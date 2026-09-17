"""`tre bench` — real bounded performance measurement on this machine."""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from tre_llm import paths
from tre_llm.hardware import collect, fingerprint
from tre_llm.planner.calibrate import PROMPT, SYSTEM, calib_fingerprint, load_cache, run_one, save_result
from tre_llm.registry import get, installed
from tre_llm.runtimes.llamacpp import find_binary, probe_version
from tre_llm.schemas import CalibrationResult, Evidence, PerformanceReport, Value

_BENCH_WARM = "Trả lời ngắn: thủ đô của Việt Nam là gì?"
_BENCH_COLD = "Kể tên ba món ăn sáng phổ biến ở Việt Nam."


def run_bench(quick: bool = True, model_id: str = "") -> PerformanceReport:
    binary = find_binary()
    if binary is None:
        raise RuntimeError("Chưa có llama-server — chạy `tre setup`.")
    inst = installed()
    if model_id:
        ids = [model_id]
    else:
        ids = list(inst)[:3]
    if not ids:
        raise RuntimeError("Chưa cài model nào — chạy `tre setup` hoặc `tre models pull`.")

    hw = collect()
    hw_fp = fingerprint(hw)
    ver = probe_version(binary)
    build = ver.get("build") or "unknown"

    results: list[CalibrationResult] = []
    for rid in ids:
        if rid not in inst:
            continue
        art = inst[rid].artifact or get(rid)
        if art is None:
            # imported model without registry entry — minimal artifact
            from tre_llm.schemas import ArtifactFile, ModelArtifact

            p = Path(inst[rid].local_path)
            art = ModelArtifact(
                id=rid, display_name=rid, upstream_repo="(import cục bộ)", upstream_model=rid,
                publisher="user-import", files=[ArtifactFile(path=p.name, size_bytes=p.stat().st_size)],
            )
        fp = calib_fingerprint(hw_fp, art, build, 4096)
        res = run_one(binary, art, Path(inst[rid].local_path), 4096, threads=8, fingerprint=fp)
        save_result(res)
        results.append(res)

    ok = [r for r in results if r.status == "ok"]
    rep = PerformanceReport(
        model_id=", ".join(ids),
        artifact_sha256=inst[ids[0]].sha256_actual if ids and ids[0] in inst else "",
        runtime_build=build,
        hardware=hw,
        samples=len(ok),
        failures=len(results) - len(ok),
        measured_at=datetime.now(UTC).isoformat(),
    )
    if ok:
        decode = [r.decode_tps.value for r in ok if r.decode_tps.value]
        ttft = [r.ttft_ms.value for r in ok if r.ttft_ms.value]
        rss = [r.peak_rss_mb.value for r in ok if r.peak_rss_mb.value]
        load = [r.load_ms.value for r in ok if r.load_ms.value]
        if decode:
            rep.decode_tps = Value(value=round(statistics.median(decode), 2), unit="tok/s", evidence=Evidence.MEASURED)
        if ttft:
            rep.ttft_ms = Value(value=round(statistics.median(ttft), 1), unit="ms", evidence=Evidence.MEASURED)
        if rss:
            rep.peak_rss_mb = Value(value=round(statistics.median(rss)), unit="MiB", evidence=Evidence.MEASURED)
        if load:
            rep.load_ms = Value(value=round(statistics.median(load), 1), unit="ms", evidence=Evidence.MEASURED)
        rep.notes.append(f"Mẫu nhỏ (n={len(ok)}) — median, không suy ra p95.")
    else:
        rep.notes.append("Tất cả candidate thất bại: " + "; ".join(r.error[:80] for r in results))

    out = paths.eval_results_dir() / f"bench-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rep.model_dump_json(indent=2), encoding="utf-8")
    rep.notes.append(f"report: {out}")
    return rep
