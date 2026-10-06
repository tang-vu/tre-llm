"""Synthetic upstream transport; routing and ChatClient parsing remain real.

These are deterministic protocol tests, not model inference evidence.
"""

import inspect
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from tre_llm.inference.client import ChatClient
from tre_llm.runtimes.manager import RunningServer
from tre_llm.schemas import PlanChoice
from tre_llm.server.app import create_app, state


def frame(delta=None, finish=None, **extra):
    data = {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}], **extra}
    return ("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode()


class GateUpstream:
    def __init__(self):
        self.paused = threading.Event()
        self.release = threading.Event()
        self.mutex = threading.Lock()
        self.active = set()
        self.max_active = 0
        self.calls = []
        self.closed = []

    def handle(self, request):
        assert request.url.path == "/v1/chat/completions"
        label = json.loads(request.content)["messages"][-1]["content"]
        with self.mutex:
            self.calls.append(label)
        if label == "http-error":
            return httpx.Response(503, text="synthetic unavailable")
        if label == "transport-error":
            raise httpx.ConnectError("synthetic connection failure")
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=GateStream(self, label)
        )


class GateStream(httpx.SyncByteStream):
    def __init__(self, upstream, label):
        self.upstream, self.label = upstream, label
        self.closed = False

    def __iter__(self):
        u = self.upstream
        with u.mutex:
            u.active.add(self.label)
            u.max_active = max(u.max_active, len(u.active))
        # Split inside multibyte UTF-8 characters as a real HTTP transport can.
        delta = {"content": self.label + " Tiếng Việt"}
        if self.label != "first":
            delta["reasoning_content"] = "Suy nghĩ"
        first = frame(delta)
        for byte in first:
            yield bytes([byte])
        if self.label == "first":
            u.paused.set()
            assert u.release.wait(10), "test did not release its synthetic upstream"
        if self.label == "read-error":
            raise httpx.ReadError("synthetic read failure")
        if self.label == "unexpected-error":
            raise RuntimeError("synthetic unexpected failure")
        yield frame({"content": " last"})
        yield frame(
            finish="stop",
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            timings={"predicted_per_second": 10.0},
        )
        yield b"data: [DONE]\n\n"

    def close(self):
        assert state.gen_lock.locked()
        if not self.closed:
            self.closed = True
            with self.upstream.mutex:
                self.upstream.active.discard(self.label)
                self.upstream.closed.append(self.label)


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(state, "current_cancel", [])
    upstream = GateUpstream()
    lock = threading.Lock()

    class ObservedLock:
        acquire = lock.acquire
        locked = lock.locked

        def release(self):
            assert not upstream.active
            assert not state.current_cancel
            lock.release()

    monkeypatch.setattr(state, "gen_lock", ObservedLock())
    # Use the real parser without constructing an unused network/proxy transport.
    provider = ChatClient.__new__(ChatClient)
    provider.base_url = "http://synthetic.invalid"
    provider.timeout = 600.0
    provider._cancel = threading.Event()
    provider._client = httpx.Client(transport=httpx.MockTransport(upstream.handle))
    generators = []
    generate_iter = provider.generate_iter

    def retain_generator(req):
        source = generate_iter(req)
        generators.append(source)
        return source

    monkeypatch.setattr(provider, "generate_iter", retain_generator)
    runtime = RunningServer(provider, None, provider.base_url, PlanChoice(artifact_id="fake"), [])
    app = create_app(runtime, "fake")
    try:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            yield SimpleNamespace(
                upstream=upstream,
                provider=provider,
                runtime=runtime,
                app=app,
                client=client,
                generators=generators,
            )
    finally:
        upstream.release.set()
        provider.close()
    assert not upstream.active
    assert not state.gen_lock.locked()
    assert state.current_cancel == []
    # Retention makes missing explicit cleanup visible without depending on GC.
    assert all(inspect.getgeneratorstate(g) == "GEN_CLOSED" for g in generators)


def request(client, kind, label):
    if kind == "persisted":
        return client.post("/api/chat", json={"message": label})
    return client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": label}], "stream": kind == "stream"},
    )


@contextmanager
def in_flight(harness, kind="stream"):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(request, harness.client, kind, "first")
        try:
            assert harness.upstream.paused.wait(5), "first request did not reach provider gate"
            yield future
        finally:
            harness.upstream.release.set()
            future.result(timeout=5)


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]


def assert_reusable(harness):
    assert not harness.upstream.active
    assert not state.gen_lock.locked()
    assert state.current_cancel == []
    assert request(harness.client, "stream", "next").status_code == 200
    assert harness.upstream.max_active == 1
