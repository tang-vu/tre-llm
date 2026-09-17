"""Shared resolution logic: pick the model to run, start or attach runtime."""

from __future__ import annotations

from pathlib import Path

from tre_llm import config
from tre_llm.cli.util import die, warn
from tre_llm.hardware import collect
from tre_llm.planner.calibrate import load_cache
from tre_llm.planner.select import build_plan
from tre_llm.registry import catalog, installed
from tre_llm.runtimes import manager
from tre_llm.runtimes.manager import RunningServer
from tre_llm.schemas import Goal, PlanChoice


def resolve_choice(model_id: str = "", goal: str = "balanced") -> tuple[PlanChoice, Path]:
    """Resolve which installed model to run + its file path."""
    inst = installed()
    if model_id:
        if model_id not in inst:
            die(f"Model '{model_id}' chưa cài. `tre models list` để xem, `tre models pull {model_id}` để tải.")
        return PlanChoice(artifact_id=model_id), Path(inst[model_id].local_path)

    if not inst:
        die("Chưa cài model nào. Chạy `tre setup` hoặc `tre models pull <id>`.")

    # Prefer the saved setting, else plan over installed models.
    from tre_llm.storage.db import get_db

    saved = get_db().get_setting("active_model")
    if saved and saved in inst:
        return PlanChoice(artifact_id=saved), Path(inst[saved].local_path)

    hw = collect()
    arts = [a for a in catalog() if a.id in inst]
    if arts:
        calib = {r.artifact_id: (r.decode_tps.value or 0) for r in load_cache().values()}
        plan = build_plan(hw, arts, Goal(goal), set(inst), calibrated_tps=calib)
        if plan.chosen:
            return plan.chosen, Path(inst[plan.chosen.artifact_id].local_path)
    # Imported models or no plan: take the first installed.
    first = next(iter(inst))
    return PlanChoice(artifact_id=first), Path(inst[first].local_path)


def start_runtime(
    model_id: str = "",
    goal: str = "balanced",
    attach_url: str = "",
    ctx_override: int = 0,
    on_adjust=None,
) -> RunningServer:
    """Attach to an external server, or launch a managed llama-server."""
    if attach_url:
        return manager.attach(attach_url)

    choice, model_path = resolve_choice(model_id, goal)
    if ctx_override:
        choice.ctx_size = ctx_override
    if not choice.threads:
        from tre_llm.hardware import collect as _collect
        from tre_llm.planner.select import _default_threads

        choice.threads = _default_threads(_collect())
    if not choice.ctx_size:
        choice.ctx_size = int(config.get("defaults", "ctx_size", default=4096))

    return manager.start_managed(
        choice, model_path, on_adjust=on_adjust or (lambda m: warn(f"Phục hồi: {m}"))
    )
