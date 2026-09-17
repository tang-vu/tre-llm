"""`tre bench` / `tre eval` / `tre report` — measurement surfaces (M4 fills in)."""

from __future__ import annotations

import typer

from tre_llm.cli.util import console, die, emit_json


def run_bench(quick: bool = False, model: str = "", json_mode: bool = False) -> None:
    from tre_llm.evaluation.bench import run_bench as _run

    res = _run(quick=quick, model_id=model)
    if json_mode:
        emit_json(res)
        return
    console.print(res.summary_vi())


def run_eval(suite: str, split: str, model: str, limit: int, judge: str, out: str) -> None:
    from tre_llm.evaluation.runner import run_suite

    rep = run_suite(suite=suite, split=split, model_id=model, limit=limit or None, judge=judge, out_dir=out or None)
    console.print(
        f"[green]Xong.[/green] {rep.summary.get('graded', 0)} câu chấm tự động, "
        f"{rep.summary.get('ungraded', 0)} câu rubric chưa chấm."
    )


def run_report(format: str, out: str) -> None:
    from tre_llm.evaluation.report import build_report

    path = build_report(format=format, out=out or None)
    console.print(f"[green]Report:[/green] {path}")
