"""Explainable model selection.

Filter order: format/architecture compatibility -> license -> resource
feasibility -> ranking by goal. Every rejection carries a reason; every choice
explains what is measured, estimated, or unknown.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tre_llm.planner.memory import estimate
from tre_llm.schemas import (
    DeploymentPlan,
    Goal,
    HardwareSnapshot,
    ModelArtifact,
    PlanChoice,
)

ALLOWED_LICENSES = {"apache-2.0", "mit", "llama-community", "gemma"}
SUPPORTED_FORMATS = {"gguf"}
SUPPORTED_ARCHES = {
    # verified or documented-compatible with llama.cpp b11022
    "qwen3.5", "qwen3", "qwen2", "llama", "gemma3", "phi3", "mistral",
}
RESERVE_RAM_MB = 2048  # keep for OS; adjusted by reserve fraction below
RESERVE_FRACTION = 0.20

# Context defaults per profile: small ctx on tiny keeps memory + prefill sane.
PROFILE_CTX = {"tiny": 4096, "lite": 8192, "core": 8192, "pro": 8192}
PROFILE_OUT = {"tiny": 512, "lite": 1024, "core": 1024, "pro": 1024}

# Rough CPU decode-speed heuristic (tok/s per GHz-core is unknowable a priori;
# used only to rank when no calibration exists — labelled ESTIMATED).
_HEURISTIC_TPS_PER_BILLION = 25.0


def _ram_budget_mb(hw: HardwareSnapshot) -> int | None:
    if hw.ram_available_mb is None:
        return None
    reserve = max(RESERVE_RAM_MB, int((hw.ram_total_mb or 0) * RESERVE_FRACTION))
    return max(0, hw.ram_available_mb - reserve)


def _compatible(artifact: ModelArtifact) -> str | None:
    if artifact.format not in SUPPORTED_FORMATS:
        return f"định dạng {artifact.format} chưa hỗ trợ"
    if artifact.architecture and artifact.architecture not in SUPPORTED_ARCHES:
        return f"kiến trúc {artifact.architecture} chưa được llama.cpp hỗ trợ"
    if artifact.license and artifact.license not in ALLOWED_LICENSES:
        return f"license {artifact.license} không đủ điều kiện phân phối"
    return None


def _default_threads(hw: HardwareSnapshot) -> int:
    cores = hw.cpu.physical_cores or hw.cpu.logical_cores or 4
    # Hyperthread siblings rarely help decode; use physical cores capped at 16.
    return max(2, min(16, cores))


def _choice(
    artifact: ModelArtifact,
    hw: HardwareSnapshot,
    goal: Goal,
    installed_ids: set[str],
) -> PlanChoice:
    ctx = min(PROFILE_CTX.get(artifact.profile, 4096), artifact.context_length or 8192)
    c = PlanChoice(
        artifact_id=artifact.id,
        ctx_size=ctx,
        max_output=PROFILE_OUT.get(artifact.profile, 1024),
        threads=_default_threads(hw),
        batch_size=512,
        ubatch_size=512,
        parallel=1,
        gpu_layers=0,
    )
    mem = estimate(artifact, c.ctx_size, parallel=c.parallel, batch_size=c.batch_size)
    c.memory = mem
    budget = _ram_budget_mb(hw)
    if budget is None:
        c.feasible = False
        c.rejection = "không đo được RAM khả dụng"
    elif mem.total_mb is not None and mem.total_mb > budget:
        c.feasible = False
        c.rejection = (
            f"ước lượng {mem.total_mb} MiB > ngân sách {budget} MiB RAM "
            f"(đã chừa {max(RESERVE_RAM_MB, int((hw.ram_total_mb or 0) * RESERVE_FRACTION))} MiB cho hệ thống)"
        )
    elif artifact.min_ram_mb and (hw.ram_total_mb or 0) < artifact.min_ram_mb:
        c.feasible = False
        c.rejection = f"RAM tổng {hw.ram_total_mb} MiB < khuyến nghị tối thiểu {artifact.min_ram_mb} MiB"
    return c


def _score(artifact: ModelArtifact, choice: PlanChoice, goal: Goal, calibrated: dict[str, float]) -> tuple:
    """Deterministic ranking tuple (lower is better)."""
    mem = choice.memory.total_mb or 0
    size = sum(f.size_bytes for f in artifact.files) / 2**30
    tps = calibrated.get(artifact.id)  # measured tok/s if calibration ran
    if goal == Goal.LIGHT:
        # smallest feasible memory, then smallest download, then id
        return (mem, size, artifact.id)
    if goal == Goal.QUALITY:
        # biggest feasible model; prefer measured speed as tiebreak
        return (-artifact.params_billion, -(tps or 0), artifact.id)
    # balanced: prefer measured tps within a quality floor; else mid params
    if tps:
        return (-(artifact.params_billion * min(tps, 30)), artifact.id)
    return (-artifact.params_billion / max(size, 0.4), artifact.id)


def build_plan(
    hw: HardwareSnapshot,
    artifacts: list[ModelArtifact],
    goal: Goal = Goal.BALANCED,
    installed_ids: set[str] | None = None,
    calibrated_tps: dict[str, float] | None = None,
    prefer_installed: bool = True,
    created_at: str | None = None,
) -> DeploymentPlan:
    """Pick a deployment for this machine and explain it in Vietnamese."""
    installed_ids = installed_ids or set()
    calibrated_tps = calibrated_tps or {}
    plan = DeploymentPlan(
        goal=goal,
        created_at=created_at or datetime.now(UTC).isoformat(),
    )

    # Hardware sanity gates.
    if hw.ram_total_mb is not None and hw.ram_total_mb < 3072:
        plan.supported = False
        plan.unsupported_reason = (
            f"RAM {hw.ram_total_mb} MiB < 3 GiB — thiết bị quá yếu cho hội thoại "
            "đa dụng. Tre chỉ đề xuất tác vụ giới hạn trên máy này."
        )

    candidates: list[PlanChoice] = []
    rejected: list[PlanChoice] = []
    for art in artifacts:
        why = _compatible(art)
        choice = _choice(art, hw, goal, installed_ids)
        if why:
            choice.feasible = False
            choice.rejection = why
        if choice.feasible:
            candidates.append(choice)
        rejected.append(choice)

    feasible_arts = {a.id: a for a in artifacts}
    scored = sorted(
        (c for c in candidates if c.feasible),
        key=lambda c: _score(feasible_arts[c.artifact_id], c, goal, calibrated_tps),
    )

    if prefer_installed:
        installed_first = [c for c in scored if c.artifact_id in installed_ids]
        if installed_first:
            scored = installed_first + [c for c in scored if c.artifact_id not in installed_ids]

    if scored:
        plan.chosen = scored[0]
        plan.rejected = [c for c in rejected if c.artifact_id != plan.chosen.artifact_id]
        art = feasible_arts[plan.chosen.artifact_id]
        plan.explanation = _explain(plan.chosen, art, hw, goal, scored[1:])
    else:
        plan.chosen = None
        plan.rejected = rejected
        plan.supported = False
        reasons = "; ".join(f"{c.artifact_id}: {c.rejection}" for c in rejected[:4])
        plan.unsupported_reason = plan.unsupported_reason or (
            f"Không có cấu hình khả thi. {reasons}"
        )
    return plan


def _explain(
    chosen: PlanChoice,
    art: ModelArtifact,
    hw: HardwareSnapshot,
    goal: Goal,
    alternatives: list[PlanChoice],
) -> list[str]:
    goal_vi = {
        Goal.LIGHT: "Nhẹ máy",
        Goal.BALANCED: "Cân bằng",
        Goal.QUALITY: "Ưu tiên chất lượng",
    }[goal]
    mem = chosen.memory
    lines = [
        f"Mục tiêu: {goal_vi}.",
        f"Model: {art.display_name} — upstream {art.upstream_repo} "
        f"({art.quantization}, {art.params_billion}B tham số, license {art.license}).",
        f"Runtime: llama.cpp (CPU{'' if chosen.gpu_layers == 0 else f' + {chosen.gpu_layers} lớp GPU'}), "
        f"ctx={chosen.ctx_size}, output≤{chosen.max_output}, threads={chosen.threads}.",
        f"Ước lượng RAM đỉnh ~{mem.total_mb} MiB ({mem.evidence.value}) — "
        f"trống hiện tại {hw.ram_available_mb} MiB.",
    ]
    if mem.assumptions:
        lines.append("Giả định: " + " | ".join(mem.assumptions))
    if alternatives:
        alts = ", ".join(c.artifact_id for c in alternatives[:3])
        lines.append(f"Phương án khả thi khác: {alts}.")
    return lines
