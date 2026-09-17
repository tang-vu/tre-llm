"""Tre-specific API routes consumed by the web UI.

Separated from app.py so the OpenAI-compat surface stays minimal. All routes
are loopback-only (Host check lives in app middleware).
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from tre_llm import paths
from tre_llm.storage.db import get_db

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- documents


class DocIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4_000_000)


@router.get("/documents")
def documents_list():
    from tre_llm.documents.service import list_documents

    return {"documents": list_documents()}


@router.post("/documents")
def documents_add(doc: DocIn):
    """Import document content sent by the UI (file picked client-side)."""
    from tre_llm.documents.service import add_document

    paths.documents_dir().mkdir(parents=True, exist_ok=True)
    safe = Path(doc.name).name
    if not safe.lower().endswith((".txt", ".md", ".markdown")):
        raise HTTPException(400, "v0.1 hỗ trợ .txt/.md — PDF cần OCR (chưa hỗ trợ).")
    f = paths.documents_dir() / f"{uuid.uuid4().hex[:8]}-{safe}"
    f.write_text(doc.content, encoding="utf-8")
    try:
        meta = add_document(f)
    except ValueError as exc:
        f.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    return meta


@router.get("/documents/{doc_id}")
def documents_get(doc_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    chunks = [
        dict(r)
        for r in db.execute(
            "SELECT id, seq, text, char_offset, char_length FROM chunks WHERE document_id=? ORDER BY seq",
            (doc_id,),
        ).fetchall()
    ]
    return {"document": dict(row), "chunks": chunks}


@router.get("/documents/chunk/{chunk_id:path}")
def documents_chunk(chunk_id: str):
    db = get_db()
    row = db.execute(
        "SELECT c.*, d.name AS doc_name FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.id=?",
        (chunk_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Chunk không tồn tại")
    return dict(row)


@router.delete("/documents/{doc_id}")
def documents_delete(doc_id: str):
    from tre_llm.documents.service import remove_document

    if not remove_document(doc_id):
        raise HTTPException(404, "Không tìm thấy tài liệu")
    return {"deleted": doc_id}


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    k: int = Field(default=4, ge=1, le=12)


@router.post("/ask")
def documents_ask(body: AskIn, request: Request):
    from tre_llm.documents.service import answer_question
    from tre_llm.server.app import state

    if state.server is None:
        raise HTTPException(503, "Runtime chưa sẵn sàng")
    if not state.gen_lock.acquire(blocking=False):
        raise HTTPException(409, "Đang bận một yêu cầu khác")
    try:
        return answer_question(
            state.server.client, body.question, model_id=state.active_model, k=body.k
        )
    finally:
        state.gen_lock.release()


# ---------------------------------------------------------------- models


@router.get("/models")
def models_list():
    from tre_llm.registry import catalog, installed

    return {
        "registry": [a.model_dump(mode="json") for a in catalog()],
        "installed": {k: v.model_dump(mode="json") for k, v in installed().items()},
        "active": get_db().get_setting("active_model"),
    }


class SelectIn(BaseModel):
    model_id: str


@router.post("/models/select")
def models_select(body: SelectIn):
    from tre_llm.registry import installed

    if body.model_id not in installed():
        raise HTTPException(404, "Model chưa cài")
    get_db().set_setting("active_model", body.model_id)
    return {"active": body.model_id, "note": "áp dụng khi khởi động lại `tre serve`"}


@router.delete("/models/{model_id}")
def models_delete(model_id: str):
    from tre_llm.registry import remove

    if not remove(model_id, delete_files=True):
        raise HTTPException(404, "Model chưa cài")
    return {"deleted": model_id}


# ---------------------------------------------------------------- runs


_run_threads: dict[str, dict] = {}


def _run_bg(kind: str, fn) -> str:
    run_id = uuid.uuid4().hex[:10]
    db = get_db()
    db.add_run(run_id, kind, model_id="", status="running")
    _run_threads[run_id] = {"status": "running"}

    def wrap():
        try:
            out = fn()
            _run_threads[run_id] = {"status": "done", "result": out}
            db.finish_run(run_id, "done", report_path=str(out) if isinstance(out, str | Path) else "")
        except Exception as exc:
            _run_threads[run_id] = {"status": "error", "error": str(exc)[:400]}
            db.finish_run(run_id, "error")

    threading.Thread(target=wrap, daemon=True).start()
    return run_id


@router.get("/runs/{run_id}")
def run_status(run_id: str):
    info = _run_threads.get(run_id)
    if info is None:
        row = get_db().execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(404, "run không tồn tại")
        info = {"status": row["status"], "report_path": row["report_path"]}
    return info


@router.post("/bench")
def bench_start(quick: bool = True):
    from tre_llm.evaluation.bench import run_bench

    def work():
        rep = run_bench(quick=quick)
        return rep.summary_vi()

    return {"run_id": _run_bg("bench", work)}


@router.get("/reports")
def reports_list():
    out = []
    for d in (paths.eval_results_dir(), paths.reports_dir()):
        if d.is_dir():
            for f in sorted(d.iterdir(), reverse=True):
                if f.is_file():
                    out.append({"name": f.name, "size": f.stat().st_size, "dir": d.parent.name})
    return {"reports": out[:50]}


@router.get("/reports/{name}")
def reports_get(name: str):
    safe = Path(name).name
    for d in (paths.eval_results_dir(), paths.reports_dir()):
        f = d / safe
        if f.is_file():
            if f.suffix == ".html":
                from fastapi.responses import HTMLResponse

                return HTMLResponse(f.read_text(encoding="utf-8"))
            return json.loads(f.read_text(encoding="utf-8"))
    raise HTTPException(404)


# ---------------------------------------------------------------- conversations


@router.get("/conversations/{conv_id}/messages")
def conv_messages(conv_id: str):
    return {"messages": get_db().messages(conv_id)}


class NewConvIn(BaseModel):
    title: str = ""


@router.post("/conversations")
def conv_new(body: NewConvIn):
    conv_id = uuid.uuid4().hex[:12]
    get_db().create_conversation(conv_id, title=body.title)
    return {"id": conv_id}


# ---------------------------------------------------------------- chat (persisted)


class ApiChatIn(BaseModel):
    conversation_id: str = ""
    message: str = Field(min_length=1, max_length=32000)
    system: str = ""
    max_tokens: int = Field(default=512, ge=1, le=8192)
    enable_thinking: bool = False


@router.post("/chat")
def api_chat(body: ApiChatIn):
    """Persisted chat used by the web UI. Streams SSE; saves both sides."""
    from fastapi.responses import StreamingResponse

    from tre_llm.schemas import GenerationRequest
    from tre_llm.server.app import state

    if state.server is None:
        raise HTTPException(503, "Runtime chưa sẵn sàng — chạy `tre setup`.")

    db = get_db()
    conv_id = body.conversation_id or uuid.uuid4().hex[:12]
    if not db.execute("SELECT 1 FROM conversations WHERE id=?", (conv_id,)).fetchone():
        db.create_conversation(conv_id, model_id=state.active_model)

    def stream():
        if not state.gen_lock.acquire(blocking=False):
            yield b"data: " + json.dumps({"type": "error", "error": "Đang bận một yêu cầu khác."}).encode() + b"\n\n"
            return
        client = state.server.client
        state.current_cancel.append(client.cancel)
        try:
            # Persist the user message only once we hold the lock — avoids
            # orphan messages when the request is rejected as busy.
            history = db.messages(conv_id)
            msgs = [{"role": m["role"], "content": m["content"]} for m in history]
            if body.system and not any(m["role"] == "system" for m in msgs):
                msgs.insert(0, {"role": "system", "content": body.system})
            msgs.append({"role": "user", "content": body.message})
            db.add_message(conv_id, "user", body.message)

            req = GenerationRequest(
                model=state.active_model,
                messages=msgs,
                max_tokens=body.max_tokens,
                enable_thinking=body.enable_thinking,
            )
            text, reasoning = "", ""
            yield b"data: " + json.dumps({"type": "conv", "id": conv_id}).encode() + b"\n\n"
            for ev in client.generate_iter(req):
                if ev.type == "token":
                    text += ev.text
                    yield b"data: " + json.dumps({"type": "token", "text": ev.text}, ensure_ascii=False).encode() + b"\n\n"
                elif ev.type == "reasoning":
                    reasoning += ev.text
                    yield b"data: " + json.dumps({"type": "reasoning", "text": ev.text}, ensure_ascii=False).encode() + b"\n\n"
                elif ev.type == "error":
                    yield b"data: " + json.dumps({"type": "error", "error": ev.error}, ensure_ascii=False).encode() + b"\n\n"
                elif ev.type == "done":
                    db.add_message(conv_id, "assistant", text, reasoning=reasoning)
                    yield b"data: " + json.dumps(
                        {"type": "done", "finish_reason": ev.finish_reason, "timings": ev.timings},
                        ensure_ascii=False,
                    ).encode() + b"\n\n"
            yield b"data: [DONE]\n\n"
        finally:
            if client.cancel in state.current_cancel:
                state.current_cancel.remove(client.cancel)
            state.gen_lock.release()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
