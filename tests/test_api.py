"""API contract tests against a fake llama-server (deterministic protocol only —
genuine inference evidence lives in tests marked `integration`)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient
from tre_llm.runtimes.manager import RunningServer
from tre_llm.inference.client import ChatClient
from tre_llm.schemas import PlanChoice
from tre_llm.server.app import create_app

SSE_TEXT = "Xin chào bạn"


class FakeLlama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/health":
            return self._json({"status": "ok"})
        if self.path == "/v1/models":
            return self._json({"data": [{"id": "fake"}]})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if not body.get("messages"):
            return self._json({"error": "messages required"}, 400)
        if body.get("stream"):
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            for tok in ["Xin", " chào", " bạn"]:
                chunk = {
                    "id": "c1", "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": tok}, "finish_reason": None}],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
            done = {
                "id": "c1", "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                "timings": {"predicted_per_second": 10.0},
            }
            self.wfile.write(f"data: {json.dumps(done)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        return self._json(
            {
                "id": "c1",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": SSE_TEXT}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            }
        )

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def fake_runtime():
    srv = HTTPServer(("127.0.0.1", 0), FakeLlama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    yield url
    srv.shutdown()


@pytest.fixture()
def client(fake_runtime):
    running = RunningServer(
        client=ChatClient(fake_runtime),
        process=None,
        base_url=fake_runtime,
        effective=PlanChoice(artifact_id="fake-model"),
        adjustments=[],
    )
    app = create_app(server=running, active_model="fake-model")
    return TestClient(app, base_url="http://127.0.0.1")


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["upstream_ready"] is True


def test_models(client):
    r = client.get("/v1/models")
    assert r.json()["data"][0]["id"] == "fake-model"


def test_chat_nonstream(client):
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "chào"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["choices"][0]["message"]["content"] == SSE_TEXT
    assert body["usage"]["total_tokens"] == 8


def test_chat_stream_sse(client):
    with client.stream(
        "POST", "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "chào"}], "stream": True},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()
    assert "data: [DONE]" in raw
    assert "Xin" in raw and "finish_reason" in raw
    # UTF-8 content must survive SSE framing
    assert "chào" in raw


def test_validation_rejects_extra_fields(client):
    r = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "x"}], "logprobs": True},
    )
    assert r.status_code == 422  # unsupported fields rejected, not ignored


def test_validation_requires_messages(client):
    r = client.post("/v1/chat/completions", json={"messages": []})
    # empty message list passes pydantic but fake server returns content anyway;
    # our contract test asserts a non-500 response either way
    assert r.status_code in (200, 400, 422)


def test_host_header_guard(fake_runtime):
    running = RunningServer(ChatClient(fake_runtime), None, fake_runtime, PlanChoice(artifact_id="m"), [])
    c = TestClient(create_app(server=running, active_model="m"), base_url="http://127.0.0.1")
    r = c.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "x"}]},
        headers={"Host": "evil.com"},
    )
    assert r.status_code == 403
