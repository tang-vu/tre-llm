"""`tre documents …` + `tre ask` — local document Q&A (implemented in M3)."""

from __future__ import annotations

from pathlib import Path

import typer

from tre_llm.cli.util import console, die, emit_json

app = typer.Typer(no_args_is_help=True)


@app.command("add", help="Nạp file .txt/.md vào chỉ mục cục bộ.")
def add(path: Path = typer.Argument(..., exists=True)) -> None:  # noqa: B008 — typer idiom
    from tre_llm.documents.service import add_document

    try:
        doc = add_document(path)
    except Exception as exc:
        die(str(exc))
    console.print(f"[green]Đã nạp:[/green] {doc['name']} — {doc['chunks']} đoạn, {doc['size_bytes']} B")


@app.command("list", help="Liệt kê tài liệu đã nạp.")
def list_(json: bool = typer.Option(False, "--json")) -> None:
    from tre_llm.documents.service import list_documents

    docs = list_documents()
    if json:
        emit_json(docs)
        return
    if not docs:
        console.print("Chưa có tài liệu. `tre documents add <file.md>`")
        return
    for d in docs:
        console.print(f"  • {d['id']}: {d['name']} — {d['chunk_count']} đoạn ({d['status']})")


@app.command("remove", help="Xoá tài liệu khỏi chỉ mục.")
def remove(doc_id: str = typer.Argument(...)) -> None:
    from tre_llm.documents.service import remove_document

    if not remove_document(doc_id):
        die(f"Không có tài liệu '{doc_id}'.")
    console.print(f"[green]Đã xoá {doc_id}.[/green]")


def run_ask(question: str, model: str = "", k: int = 4) -> None:
    from tre_llm.cli.common import start_runtime
    from tre_llm.documents.service import answer_question

    try:
        srv = start_runtime(model_id=model)
    except Exception as exc:
        die(str(exc))
    try:
        out = answer_question(srv.client, question, model_id=srv.effective.artifact_id, k=k)
        console.print(out["answer"])
        if out["citations"]:
            console.print("\n[bold]Nguồn trích:[/bold]")
            for c in out["citations"]:
                console.print(f"  [{c['n']}] {c['document']} — “{c['excerpt'][:120]}…”")
        else:
            console.print("[dim]Không có đoạn tài liệu nào đủ liên quan.[/dim]")
    finally:
        srv.stop()
