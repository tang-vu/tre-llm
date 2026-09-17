"""Planner invariants: feasibility, goals, unified memory, unknown metadata."""

from datetime import UTC, datetime

from tre_llm.planner.memory import estimate, kv_cache_mb
from tre_llm.planner.select import build_plan
from tre_llm.schemas import (
    ArtifactFile,
    CpuInfo,
    Evidence,
    Goal,
    HardwareSnapshot,
    ModelArtifact,
)


def hw(ram_total=16384, ram_avail=None, gpus=None):
    return HardwareSnapshot(
        collected_at=datetime.now(UTC).isoformat(),
        os="linux",
        cpu=CpuInfo(model="test", physical_cores=8, logical_cores=16),
        ram_total_mb=ram_total,
        ram_available_mb=ram_avail if ram_avail is not None else int(ram_total * 0.8),
        gpus=gpus or [],
    )


def art(rid, size_mb=500, params=0.8, profile="tiny", arch="qwen3.5", lic="apache-2.0", arch_meta=None):
    return ModelArtifact(
        id=rid,
        display_name=rid,
        upstream_repo="org/model",
        upstream_model="org/model",
        publisher="org",
        files=[ArtifactFile(path="m.gguf", size_bytes=size_mb * 2**20, sha256="0" * 64)],
        params_billion=params,
        profile=profile,
        license=lic,
        architecture=arch,
        arch_meta=(
            {"n_layers": 24, "kv_heads": 2, "head_dim": 256, "full_attn_interval": 4, "hybrid": True}
            if arch_meta is None
            else arch_meta
        ),
    )


def test_hybrid_kv_is_much_smaller_than_dense():
    hybrid = art("h", arch_meta={"n_layers": 24, "kv_heads": 2, "head_dim": 256, "full_attn_interval": 4, "linear_kv_heads": 16, "linear_key_dim": 128, "linear_val_dim": 128, "hybrid": True})
    dense = art("d", arch_meta={"n_layers": 36, "kv_heads": 8, "head_dim": 128, "hybrid": False})
    kh, _ = kv_cache_mb(hybrid, 8192)
    kd, _ = kv_cache_mb(dense, 8192)
    # hybrid should be far smaller than dense at same ctx
    assert kh < kd / 3


def test_unknown_arch_gets_conservative_bound():
    a = art("u", arch_meta={})
    kv, notes = kv_cache_mb(a, 4096)
    assert kv > 0
    assert any("chặn trên" in n or "chưa rõ" in n for n in notes)


def test_estimate_is_labelled_estimated_with_components():
    e = estimate(art("x", size_mb=532), ctx_size=4096)
    assert e.evidence == Evidence.ESTIMATED
    assert e.total_mb and e.total_mb > 532 / 1.048  # > weights
    assert "weights_mb" in e.components and "safety_margin_mb" in e.components


def test_infeasible_when_estimate_exceeds_budget():
    big = art("huge", size_mb=9000, params=30, profile="pro")
    plan = build_plan(hw(ram_total=8192, ram_avail=4000), [big], Goal.BALANCED)
    assert plan.chosen is None
    assert plan.supported is False
    assert "không" in plan.unsupported_reason.lower() or "RAM" in plan.unsupported_reason


def test_light_goal_prefers_small():
    tiny = art("t", size_mb=500, params=0.8, profile="tiny")
    pro = art("p", size_mb=4800, params=8, profile="pro", arch_meta={"n_layers": 36, "kv_heads": 8, "head_dim": 128, "hybrid": False})
    plan = build_plan(hw(ram_total=32768, ram_avail=28000), [pro, tiny], Goal.LIGHT)
    assert plan.chosen and plan.chosen.artifact_id == "t"


def test_quality_goal_prefers_big_when_feasible():
    tiny = art("t", size_mb=500, params=0.8, profile="tiny")
    pro = art("p", size_mb=4800, params=8, profile="pro", arch_meta={"n_layers": 36, "kv_heads": 8, "head_dim": 128, "hybrid": False})
    plan = build_plan(hw(ram_total=32768, ram_avail=28000), [tiny, pro], Goal.QUALITY)
    assert plan.chosen and plan.chosen.artifact_id == "p"


def test_deterministic_tiebreak():
    a1 = art("aaa", size_mb=500)
    a2 = art("bbb", size_mb=500)
    p1 = build_plan(hw(32768, 28000), [a1, a2], Goal.LIGHT)
    p2 = build_plan(hw(32768, 28000), [a2, a1], Goal.LIGHT)
    assert p1.chosen.artifact_id == p2.chosen.artifact_id == "aaa"


def test_very_low_ram_returns_unsupported():
    plan = build_plan(hw(ram_total=2048, ram_avail=1500), [art("t")], Goal.LIGHT)
    assert plan.supported is False


def test_incompatible_license_rejected():
    bad = art("bad", lic="cc-by-nc-4.0")
    plan = build_plan(hw(32768, 28000), [bad], Goal.BALANCED)
    assert plan.chosen is None
    assert any("license" in (c.rejection or "") for c in plan.rejected)


def test_calibrated_tps_changes_balanced_choice():
    slow = art("slow", size_mb=500, params=4, profile="core", arch_meta={"n_layers": 36, "kv_heads": 8, "head_dim": 128, "hybrid": False})
    fast = art("fast", size_mb=500, params=0.8, profile="tiny")
    plan = build_plan(
        hw(32768, 28000), [slow, fast], Goal.BALANCED, calibrated_tps={"slow": 5.0, "fast": 30.0}
    )
    assert plan.chosen is not None
    # fast model should win on balanced when measured speed is known
    assert plan.chosen.artifact_id == "fast"
