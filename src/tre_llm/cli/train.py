"""`tre train …` — Tre Adapt pipeline commands (implemented in M4)."""

from __future__ import annotations

import typer

from tre_llm.cli.util import console, die, emit_json

app = typer.Typer(no_args_is_help=True)


@app.command("preflight", help="Kiểm tra tài nguyên + đường dẫn trước khi train.")
def preflight(
    recipe: str = typer.Option(..., "--recipe"),
    json: bool = typer.Option(False, "--json"),
) -> None:
    from tre_llm.training.preflight import run_preflight

    try:
        rep = run_preflight(recipe)
    except Exception as exc:
        die(str(exc))
    if json:
        emit_json(rep)
        return
    for line in rep["lines"]:
        console.print(line, markup=False)  # lines may contain [train] etc.
    if not rep["ok"]:
        raise SystemExit(2)


@app.command("prepare", help="Chuẩn bị dữ liệu SFT từ manifest (dedupe, split deterministic).")
def prepare(
    recipe: str = typer.Option(..., "--recipe"),
    json: bool = typer.Option(False, "--json"),
) -> None:
    from tre_llm.training.dataprep import prepare as _prep

    try:
        stats = _prep(recipe)
    except Exception as exc:
        die(str(exc))
    if json:
        emit_json(stats)
        return
    console.print(f"[green]{stats['total_rows']} dòng[/green] → {stats['prepared_file']}")
    console.print(f"  train={stats['train_rows']} eval={stats['eval_rows']} "
                  f"dup={stats['dropped_dup']} invalid={stats['dropped_invalid']}")
    console.print(f"  sha256: {stats['prepared_sha256'][:16]}…")
    console.print(f"  [yellow]{stats['note']}[/yellow]")


@app.command("validate", help="Kiểm tra dữ liệu đã chuẩn bị (schema, tiếng Việt, leakage).")
def validate(
    data: str = typer.Option(..., "--data", help="Đường dẫn prepared.jsonl"),
    json: bool = typer.Option(False, "--json"),
) -> None:
    from tre_llm.training.dataprep import validate as _val

    rep = _val(data)
    if json:
        emit_json(rep)
        return
    if rep["ok"]:
        console.print(f"[green]OK[/green] — {rep['stats']['rows']} dòng, sha256 {rep['stats']['sha256'][:16]}…")
    else:
        console.print("[red]Dữ liệu không đạt:[/red]")
        for i in rep["issues"]:
            console.print(f"  - {i}")
        raise SystemExit(2)


@app.command("run", help="Chạy SFT/LoRA theo recipe (bounded).")
def run_(
    recipe: str = typer.Option(..., "--recipe"),
    json: bool = typer.Option(False, "--json"),
) -> None:
    from tre_llm.training.run import run_training

    try:
        rep = run_training(recipe)
    except Exception as exc:
        die(str(exc))
    if json:
        emit_json(rep)
        return
    console.print(rep["summary"])
