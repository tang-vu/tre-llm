"""`tre plan` — build and explain a deployment plan without downloading."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from tre_llm.cli.util import console, die, emit_json
from tre_llm.hardware import collect, fingerprint
from tre_llm.planner.calibrate import load_cache
from tre_llm.planner.select import build_plan
from tre_llm.registry import catalog, installed
from tre_llm.schemas import Goal


def run(goal: str = "balanced", json_mode: bool = False) -> None:
    try:
        g = Goal(goal)
    except ValueError:
        die("--goal phải là light | balanced | quality")

    hw = collect()
    calib = {r.artifact_id: (r.decode_tps.value or 0) for r in load_cache().values()}
    plan = build_plan(hw, catalog(), g, set(installed()), calibrated_tps=calib)
    plan.hardware_fingerprint = fingerprint(hw)

    if json_mode:
        emit_json(plan)
        return

    if not plan.supported or plan.chosen is None:
        console.print(Panel(f"[red]{plan.unsupported_reason}[/red]", title="Không khả thi", border_style="red"))
        if plan.rejected:
            t = Table(title="Các phương án bị loại")
            t.add_column("Model")
            t.add_column("Lý do")
            for c in plan.rejected:
                t.add_row(c.artifact_id, c.rejection)
            console.print(t)
        raise typer.Exit(2)

    console.print(Panel("\n".join(f"  {l}" for l in plan.explanation), title=f"[bold green]Kế hoạch đề xuất — {plan.chosen.artifact_id}[/bold green]", border_style="green"))

    if plan.rejected:
        t = Table(title="Phương án khác / bị loại", show_lines=False)
        t.add_column("Model")
        t.add_column("RAM ước lượng")
        t.add_column("Khả thi")
        t.add_column("Ghi chú")
        for c in plan.rejected:
            t.add_row(
                c.artifact_id,
                f"{c.memory.total_mb} MiB" if c.memory.total_mb else "?",
                "[green]có[/green]" if c.feasible else "[red]không[/red]",
                c.rejection or ("không chọn theo mục tiêu" if c.feasible else ""),
            )
        console.print(t)
    console.print("[dim]Các con số RAM là ước lượng bảo thủ; `tre bench --quick` sẽ đo thật.[/dim]")
