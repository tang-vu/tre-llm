"""Tests for the Tre-specific /api/* surface used by the web UI.

Uses the same fake llama-server as test_api.py — protocol-level tests only;
real inference evidence lives in integration tests.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from tre_llm.inference.client import ChatClient
from tre_llm.runtimes.manager import RunningServer
from tre_llm.schemas import PlanChoice
from tre_llm.server.app import create_app, state


class FakeLlama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/health":
            return self._json({"status": "ok"})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("content-length", 0))
        self.rfile.read(n)  # consume request body
        # Always stream back a short Vietnamese answer.
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for tok in ["Tài", " liệu", " nói…"]:
            chunk = {
                "id": "c1", "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"content": tok}, "finish_reason": None}],
            }
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        done = {
            "id": "c1", "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "timings": {"predicted_per_second": 12.5},
        }
        self.wfile.write(f"data: {json.dumps(done)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

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


def _events(raw: str) -> list[dict]:
    out = []
    for frame in raw.split("\n\n"):
        for line in frame.splitlines():
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                out.append(json.loads(line[5:].strip()))
    return out


def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["active_model"] == "fake-model"
    assert body["upstream_ready"] is True


def test_hardware_and_plan(client):
    r = client.get("/api/hardware")
    assert r.status_code == 200
    assert "cpu" in r.json() and "ram_total_mb" in r.json()
    r = client.get("/api/plan?goal=balanced")
    assert r.status_code == 200
    plan = r.json()
    assert "supported" in plan and "explanation" in plan


def test_models_registry_surface(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    body = r.json()
    assert "registry" in body and "installed" in body and "active" in body
    # selecting an uninstalled model must fail cleanly
    r = client.post("/api/models/select", json={"model_id": "khong-ton-tai"})
    assert r.status_code == 404


def test_document_roundtrip(client):
    r = client.post("/api/documents", json={
        "name": "ghi-chu.md",
        "content": "# Ghi chú\n\nHà Nội có 12 quận nội thành theo ghi chú này.\n" * 20,
    })
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]

    r = client.get("/api/documents")
    assert any(d["id"] == doc_id for d in r.json()["documents"])

    # Accentless query must still match accented content.
    r = client.post("/api/ask", json={"question": "Ha Noi co bao nhieu quan noi thanh?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] and isinstance(body["citations"], list)

    r = client.delete(f"/api/documents/{doc_id}")
    assert r.status_code == 200
    r = client.get("/api/documents")
    assert not any(d["id"] == doc_id for d in r.json()["documents"])


def test_document_rejects_bad_extension(client):
    r = client.post("/api/documents", json={"name": "x.pdf", "content": "..."})
    assert r.status_code == 400


def test_chat_stream_persists(client):
    with client.stream(
        "POST", "/api/chat",
        json={"message": "Chào bạn, tôi cần giúp"},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode("utf-8")
    assert "data: [DONE]" in raw
    evs = _events(raw)
    types = [e["type"] for e in evs]
    assert types[0] == "conv"
    assert "token" in types and types[-1] == "done"
    conv_id = evs[0]["id"]

    # Both sides persisted, UTF-8 intact.
    r = client.get(f"/api/conversations/{conv_id}/messages")
    msgs = r.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Tài liệu nói…"


def test_chat_reuses_conversation_history(client):
    with client.stream("POST", "/api/chat", json={"message": "câu một"}) as r:
        evs = _events(r.read().decode("utf-8"))
    conv_id = evs[0]["id"]
    with client.stream(
        "POST", "/api/chat",
        json={"conversation_id": conv_id, "message": "câu hai"},
    ) as r:
        r.read()
    r = client.get(f"/api/conversations/{conv_id}/messages")
    roles = [m["role"] for m in r.json()["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_chat_busy_rejects_second(client):
    # Hold the generation lock; a second /api/chat must fail inside the stream.
    state.gen_lock.acquire()
    try:
        with client.stream("POST", "/api/chat", json={"message": "x"}) as r:
            evs = _events(r.read().decode("utf-8"))
        assert any(e["type"] == "error" and "bận" in e["error"] for e in evs)
        # And no orphan user message was persisted.
        conv_id = evs[0]["id"] if evs and evs[0]["type"] == "conv" else None
        assert conv_id is None  # conv event is only emitted after lock
    finally:
        state.gen_lock.release()


def test_conversation_lifecycle(client):
    r = client.post("/api/conversations", json={"title": "thử"})
    conv_id = r.json()["id"]
    r = client.get("/api/conversations")
    assert any(c["id"] == conv_id for c in r.json())
    r = client.delete(f"/api/conversations/{conv_id}")
    assert r.status_code == 200
    r = client.get("/api/conversations")
    assert not any(c["id"] == conv_id for c in r.json())


def test_chat_requires_runtime():
    app = create_app(server=None, active_model="")
    c = TestClient(app, base_url="http://127.0.0.1")
    r = c.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503


def test_document_upload_pdf_base64(client):
    """POST /api/documents accepts PDF bytes via content_base64."""
    import base64

    from tests.test_documents import _minimal_pdf

    payload = base64.b64encode(_minimal_pdf("Da Nang la thanh pho mien Trung")).decode()
    r = client.post("/api/documents", json={
        "name": "danang.pdf", "content_base64": payload,
    })
    assert r.status_code == 200, r.text
    assert r.json()["chunks"] >= 1
    # and it is searchable through the normal path
    r2 = client.post("/api/ask", json={"question": "Da Nang o dau", "k": 3})
    assert r2.status_code == 200

    bad = client.post("/api/documents", json={
        "name": "x.pdf", "content_base64": "!!!not-base64!!!",
    })
    assert bad.status_code == 400


def test_models_select_hot_swap(client, monkeypatch, tmp_path):
    """Select on a managed runtime stops old proc and starts the new model."""
    from tre_llm.registry.store import register
    from tre_llm.runtimes import manager
    from tre_llm.schemas import InstalledModel

    # Two fake installed models: current active + target.
    for mid in ("fake-model", "new-model"):
        register(InstalledModel(
            registry_id=mid, artifact=None,
            local_path=str(tmp_path / f"{mid}.gguf"), sha256_actual="x",
            installed_at="2026-01-01T00:00:00+00:00", source="imported",
        ))

    class _Proc:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    old_proc = _Proc()
    assert state.server is not None
    state.server.process = old_proc  # pretend managed (not attached)

    started: list[str] = []

    def fake_start(rid, path, **kw):
        started.append(rid)
        return RunningServer(
            client=state.server.client if state.server else ChatClient("http://127.0.0.1:1"),
            process=_Proc(), base_url="http://127.0.0.1:1",
            effective=PlanChoice(artifact_id=rid), adjustments=[],
        )

    monkeypatch.setattr(manager, "start_for_model", fake_start)
    try:
        r = client.post("/api/models/select", json={"model_id": "new-model"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["applied"] is True and body["active"] == "new-model"
        assert old_proc.stopped is True
        assert started == ["new-model"]
        assert state.active_model == "new-model"
    finally:
        state.active_model = "fake-model"
