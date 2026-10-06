"""Actual ASGI failures/disconnects, with retained generators to detect leaks."""

import asyncio
import importlib
import inspect
import json
import threading

import anyio
import pytest

from tests.generation_helpers import assert_reusable
from tre_llm.server.app import state
from tre_llm.server.streaming import GenerationStreamingResponse


async def asgi_lifecycle(harness, mode, spec):
    body = json.dumps({"messages": [{"role": "user", "content": "first"}], "stream": True}).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec},
        "http_version": "1.1",
        "scheme": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions",
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"host", b"127.0.0.1"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 1000),
        "server": ("127.0.0.1", 80),
    }
    sent_body = False
    sent = []
    disconnect = anyio.Event()
    failed_send = anyio.Event()
    finished = anyio.Event()
    errors = []
    observation = {}

    async def receive():
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": body, "more_body": False}
        if mode == "disconnect_before_start":
            return {"type": "http.disconnect"}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if mode == "fail_start" and message["type"] == "http.response.start":
            raise OSError("synthetic header send failure")
        if message["type"] == "http.response.body" and message.get("body"):
            if mode == "fail_body":
                raise OSError("synthetic body send failure")
            if mode in (
                "fail_while_next_running",
                "disconnect_while_next_running",
                "cancel_task_while_next_running",
            ):
                assert await anyio.to_thread.run_sync(harness.upstream.paused.wait, 3)
                if mode == "disconnect_while_next_running":
                    disconnect.set()
                failed_send.set()
                if mode == "cancel_task_while_next_running":
                    asyncio.current_task().cancel()
                    await anyio.sleep(0)
                if mode == "fail_while_next_running":
                    raise OSError("synthetic failure while provider is still running")

    async def run():
        try:
            await harness.app(scope, receive, send)
        except BaseException as exc:
            errors.append(type(exc).__name__)
        finally:
            finished.set()

    async with anyio.create_task_group() as group:
        group.start_soon(run)
        if mode in (
            "fail_while_next_running",
            "disconnect_while_next_running",
            "cancel_task_while_next_running",
        ):
            with anyio.fail_after(5):
                await failed_send.wait()
                await anyio.wait_all_tasks_blocked()
            observation["app_finished_while_provider_blocked"] = finished.is_set()
            observation["lock_while_provider_blocked"] = state.gen_lock.locked()
            observation["provider_active_before_release"] = list(harness.upstream.active)
            observation["cancel_callbacks_before_release"] = len(state.current_cancel)
            harness.upstream.release.set()
        elif mode == "cancel_during_setup":
            assert await anyio.to_thread.run_sync(harness.constructed.wait, 3)
            observation["lock_before_invocation"] = state.gen_lock.locked()
            group.cancel_scope.cancel()
            harness.resume_construction.set()
            with anyio.CancelScope(shield=True), anyio.fail_after(5):
                await finished.wait()
        else:
            harness.upstream.release.set()
        with anyio.fail_after(5):
            await finished.wait()
    observation.update(
        errors=errors,
        provider_calls=list(harness.upstream.calls),
        provider_active_after_app=list(harness.upstream.active),
        provider_closed=list(harness.upstream.closed),
        cancel_callbacks_after_app=len(state.current_cancel),
        response_types=[m["type"] for m in sent],
    )
    return observation


@pytest.mark.parametrize(
    "mode,spec",
    [
        ("fail_start", "2.4"),
        ("fail_body", "2.4"),
        ("fail_while_next_running", "2.4"),
        ("disconnect_before_start", "2.3"),
        ("disconnect_while_next_running", "2.3"),
        ("cancel_task_while_next_running", "2.4"),
    ],
)
def test_asgi_cleanup_closes_sources_before_release(harness, monkeypatch, mode, spec):
    captured = []

    class CapturedResponse(GenerationStreamingResponse):
        def __init__(self, content, lock):
            def capture_source():
                assert state.gen_lock.locked()
                self.source = content()
                return self.source

            super().__init__(capture_source, lock)
            captured.append(self)
            assert not state.gen_lock.locked()

    monkeypatch.setattr(
        importlib.import_module("tre_llm.server.app"), "GenerationStreamingResponse", CapturedResponse
    )
    observed = anyio.run(asgi_lifecycle, harness, mode, spec)
    if mode in ("fail_while_next_running", "disconnect_while_next_running", "cancel_task_while_next_running"):
        assert observed["app_finished_while_provider_blocked"] is False
        assert observed["lock_while_provider_blocked"] is True
        assert observed["provider_active_before_release"] == ["first"]
        assert observed["cancel_callbacks_before_release"] == 1
    assert len(captured) == 1
    assert inspect.getgeneratorstate(captured[0].source) == "GEN_CLOSED"
    assert observed["provider_active_after_app"] == []
    assert observed["cancel_callbacks_after_app"] == 0
    assert observed["provider_closed"] == observed["provider_calls"]
    if mode.startswith("fail"):
        assert observed["errors"] == ["OSError"]
    elif mode == "cancel_task_while_next_running":
        assert observed["errors"] == ["CancelledError"]
    else:
        assert observed["errors"] == []
    # Cleanup may be retried without releasing a newer request's lock.
    state.gen_lock.acquire()
    try:
        captured[0]._stream.close()
        assert state.gen_lock.locked()
    finally:
        state.gen_lock.release()
    assert_reusable(harness)


def test_cancellation_before_response_invocation_does_not_orphan_lock(harness, monkeypatch):
    harness.constructed = threading.Event()
    harness.resume_construction = threading.Event()
    responses = []

    class PausedResponse(GenerationStreamingResponse):
        def __init__(self, source, lock):
            super().__init__(source, lock)
            responses.append(self)
            harness.constructed.set()
            assert harness.resume_construction.wait(5)

    with monkeypatch.context() as patch:
        patch.setattr(
            importlib.import_module("tre_llm.server.app"), "GenerationStreamingResponse", PausedResponse
        )
        observed = anyio.run(asgi_lifecycle, harness, "cancel_during_setup", "2.4")
    assert len(responses) == 1
    assert observed["lock_before_invocation"] is False
    assert observed["provider_calls"] == []
    assert_reusable(harness)


def test_cleanup_failure_still_unregisters_cancel_and_releases_once(harness, monkeypatch):
    responses = []

    class RetainedResponse(GenerationStreamingResponse):
        def __init__(self, source, lock):
            super().__init__(source, lock)
            responses.append(self)

    with monkeypatch.context() as patch:
        from tests.generation_helpers import GateStream

        close = GateStream.close

        def failed_close(stream):
            # The provider context closes its transport then reports an error.
            assert state.gen_lock.locked()
            close(stream)
            raise RuntimeError("synthetic cleanup failure")

        patch.setattr(GateStream, "close", failed_close)
        patch.setattr(
            importlib.import_module("tre_llm.server.app"), "GenerationStreamingResponse", RetainedResponse
        )
        observed = anyio.run(asgi_lifecycle, harness, "fail_body", "2.4")
    assert observed["errors"]  # Middleware may preserve the send error instead.
    assert len(responses) == 1
    assert not harness.upstream.active and state.current_cancel == []
    state.gen_lock.acquire()
    try:
        responses[0]._stream.close()
        assert state.gen_lock.locked()
    finally:
        state.gen_lock.release()
    assert_reusable(harness)
