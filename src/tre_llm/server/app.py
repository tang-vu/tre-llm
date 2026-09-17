"""TreLLM local server — FastAPI app.

Surfaces:
- GET  /health                       liveness (public)
- GET  /v1/models                    installed + active model (OpenAI-style)
- POST /v1/chat/completions          streaming + non-streaming chat
- GET  /api/*                        Tre-specific: hardware, plan, status, docs
- GET  /                             prebuilt web UI (same-origin, no CDN)

Security: loopback by default; Host/Origin checked for mutating endpoints;
no telemetry, no external calls except user-initiated model downloads.
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from tre_llm import paths
from tre_llm.inference.client import ChatClient, GenerationResult
from tre_llm.runtimes.manager import RunningServer
from tre_llm.schemas import GenerationRequest
from tre_llm.storage.db import get_db
from tre_llm.version import __version__

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ChatMessageIn(BaseModel):
    role: str
    content: str

    @property
    def role_ok(self) -> bool:
        return self.role in ("system", "user", "assistant")


class ChatCompletionIn(BaseModel):
    """Deliberately scoped OpenAI subset. Unsupported fields are rejected,
    not silently ignored."""

    model: str = "default"
    messages: list[ChatMessageIn]
    max_tokens: int = Field(default=512, ge=1, le=32768)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.8, ge=0, le=1)
    top_k: int = Field(default=20, ge=-1)
    presence_penalty: float = Field(default=1.5, ge=-2, le=2)
    stream: bool = False
    stop: list[str] | None = None
    chat_template_kwargs: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}

    @field_validator("messages")
    @classmethod
    def _messages_ok(cls, msgs: list[ChatMessageIn]) -> list[ChatMessageIn]:
        if not msgs:
            raise ValueError("messages không được rỗng")
        for m in msgs:
            if not m.role_ok:
                raise ValueError(f"role không hỗ trợ: {m.role}")
            if not isinstance(m.content, str) or not m.content.strip():
                raise ValueError("content rỗng")
        return msgs


class AppState:
    server: RunningServer | None = None
    active_model: str = ""
    started_at: str = ""
    gen_lock = threading.Lock()
    current_cancel: list = []  # cancel callables of in-flight generations


state = AppState()


def create_app(server: RunningServer | None = None, active_model: str = "") -> FastAPI:
    state.server = server
    state.active_model = active_model
    state.started_at = datetime.now(UTC).isoformat()

    app = FastAPI(title="TreLLM", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],  # same-origin only; explicit LAN mode would reconfigure this
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def host_check(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host and host not in ALLOWED_HOSTS and request.url.path.startswith(("/v1/", "/api/")):
            return JSONResponse({"error": "invalid host"}, status_code=403)
        if request.method in ("POST", "DELETE", "PUT", "PATCH"):
            origin = request.headers.get("origin")
            if origin:
                host_ok = any(h in origin for h in ("127.0.0.1", "localhost", "[::1]"))
                if not host_ok:
                    return JSONResponse({"error": "invalid origin"}, status_code=403)
        return await call_next(request)

    # ------------------------------------------------------------ openai subset

    @app.get("/health")
    def health():
        upstream = state.server.client.health() if state.server else False
        return {
            "status": "ok",
            "version": __version__,
            "upstream_ready": upstream,
            "active_model": state.active_model,
        }

    @app.get("/v1/models")
    def models():
        data = []
        if state.active_model:
            data.append(
                {
                    "id": state.active_model,
                    "object": "model",
                    "created": 0,
                    "owned_by": "tre-llm (upstream model giữ nguyên tên gốc)",
                }
            )
        return {"object": "list", "data": data}

    @app.post("/v1/chat/completions")
    def chat_completions(body: ChatCompletionIn):
        if state.server is None:
            raise HTTPException(503, "Chưa có runtime — chạy `tre setup` trước.")
        if not state.gen_lock.acquire(blocking=False):
            raise HTTPException(409, "Một yêu cầu khác đang chạy. Máy cục bộ xử lý tuần tự.")
        try:
            return _chat(body)
        finally:
            state.gen_lock.release()

    def _chat(body: ChatCompletionIn):
        req = GenerationRequest(
            model=body.model if body.model != "default" else state.active_model,
            messages=[m.model_dump() for m in body.messages],
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            top_p=body.top_p,
            top_k=body.top_k,
            presence_penalty=body.presence_penalty,
            stream=True,
            enable_thinking=(body.chat_template_kwargs or {}).get("enable_thinking"),
            stop=body.stop,
        )
        client = state.server.client

        if body.stream:
            return StreamingResponse(
                _sse_stream(req, client), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        result = client.generate(req)
        if result.error:
            raise HTTPException(502, f"Upstream lỗi: {result.error[:400]}")
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
            "object": "chat.completion",
            "created": int(datetime.now(UTC).timestamp()),
            "model": state.active_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result.text,
                        **({"reasoning_content": result.reasoning} if result.reasoning else {}),
                    },
                    "finish_reason": result.finish_reason or "stop",
                }
            ],
            "usage": result.usage,
            "timings": result.timings,  # tre extension: real decode/prefill rates
        }

    def _sse_stream(req: GenerationRequest, client: ChatClient) -> Iterator[bytes]:
        cid = f"chatcmpl-{uuid.uuid4().hex[:16]}"
        state.current_cancel.append(client.cancel)
        try:
            for ev in client.generate_iter(req):
                if ev.type == "token" or ev.type == "reasoning":
                    delta = (
                        {"content": ev.text}
                        if ev.type == "token"
                        else {"reasoning_content": ev.text}
                    )
                    chunk = {
                        "id": cid,
                        "object": "chat.completion.chunk",
                        "created": int(datetime.now(UTC).timestamp()),
                        "model": state.active_model,
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode()
                elif ev.type == "error":
                    err = {"id": cid, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}], "error": ev.error}
                    yield f"data: {json.dumps(err)}\n\n".encode()
                elif ev.type == "done":
                    chunk = {
                        "id": cid,
                        "object": "chat.completion.chunk",
                        "created": int(datetime.now(UTC).timestamp()),
                        "model": state.active_model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": ev.finish_reason}],
                        "usage": ev.usage,
                        "timings": ev.timings,
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode()
            yield b"data: [DONE]\n\n"
        finally:
            if client.cancel in state.current_cancel:
                state.current_cancel.remove(client.cancel)

    # ------------------------------------------------------------ tre api

    @app.get("/api/status")
    def api_status():
        from tre_llm.registry import installed

        return {
            "version": __version__,
            "active_model": state.active_model,
            "started_at": state.started_at,
            "installed": list(installed()),
            "upstream_ready": state.server.client.health() if state.server else False,
        }

    @app.get("/api/hardware")
    def api_hardware():
        from tre_llm.hardware import collect

        return collect().model_dump(mode="json")

    @app.get("/api/plan")
    def api_plan(goal: str = "balanced"):
        from tre_llm.hardware import collect, fingerprint
        from tre_llm.planner.select import build_plan
        from tre_llm.registry import catalog, installed
        from tre_llm.schemas import Goal

        hw = collect()
        plan = build_plan(hw, catalog(), Goal(goal), set(installed()))
        plan.hardware_fingerprint = fingerprint(hw)
        return plan.model_dump(mode="json")

    @app.get("/api/conversations")
    def api_conversations():
        return get_db().list_conversations()

    @app.delete("/api/conversations/{conv_id}")
    def api_delete_conversation(conv_id: str):
        get_db().delete_conversation(conv_id)
        return {"deleted": conv_id}

    @app.post("/api/cancel")
    def api_cancel():
        for cancel in list(state.current_cancel):
            cancel()
        return {"cancelled": len(state.current_cancel)}

    # ------------------------------------------------------------ static UI

    @app.get("/", response_class=HTMLResponse)
    def index():
        html = _ui_index()
        if html is None:
            return HTMLResponse(
                "<h1>TreLLM</h1><p>UI chưa được build. API tại /v1/* và /api/*.</p>"
            )
        return HTMLResponse(html)

    return app


def _ui_dir() -> Path | None:
    try:
        from importlib import resources

        res = resources.files("tre_llm.webui")
        p = Path(str(res))
        if p.is_dir():
            return p
    except (ImportError, TypeError, FileNotFoundError):
        pass
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "apps" / "web" / "dist"
        if cand.is_dir():
            return cand
    return None


def _ui_index() -> str | None:
    d = _ui_dir()
    if d and (d / "index.html").is_file():
        return (d / "index.html").read_text(encoding="utf-8")
    return None


def mount_static(app: FastAPI) -> None:
    from fastapi.staticfiles import StaticFiles

    d = _ui_dir()
    if d and (d / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=d / "assets"), name="assets")
