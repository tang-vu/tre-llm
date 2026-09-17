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
        console.print(line)
    if not rep["ok"]:
        raise typer.Exit(2)


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
