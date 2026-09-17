"""Bounded calibration: run a fixed Vietnamese workload against an installed
model, measure TTFT/decode/RSS, cache results under a versioned fingerprint.

Hard limits (developer-configurable in configs/defaults.yaml):
- <=120 s per candidate, <=3 candidates per run.
- One generation per candidate; no catalog-wide downloads.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from tre_llm import paths
from tre_llm.inference.client import ChatClient
from tre_llm.runtimes.llamacpp import LlamaCppProcess, LaunchConfig, probe_version
from tre_llm.schemas import (
    CalibrationResult,
    GenerationRequest,
    ModelArtifact,
    Value,
    Evidence,
)

CALIBRATION_TIMEOUT_S = 120
MAX_CANDIDATES = 3

# Fixed Vietnamese workload — deterministic prompt, bounded output.
PROMPT = (
    "Hãy viết đoạn giới thiệu ngắn về thành phố Hà Nội cho một bài thuyết trình, "
    "khoảng 5 câu, giọng văn trang trọng."
)
SYSTEM = "Bạn là trợ lý AI trả lời bằng tiếng Việt chuẩn mực."


def calib_fingerprint(hw_fp: str, artifact: ModelArtifact, runtime_build: str, ctx: int) -> str:
    payload = {
        "v": 2,
        "hw": hw_fp,
        "artifact": artifact.id,
        "sha": artifact.files[0].sha256 if artifact.files else "",
        "rt": runtime_build,
        "ctx": ctx,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]


def load_cache() -> dict[str, CalibrationResult]:
    p = paths.calibration_cache_path()
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for k, v in raw.items():
        try:
            out[k] = CalibrationResult.model_validate(v)
        except Exception:
            continue
    return out


def save_result(res: CalibrationResult) -> None:
    cache = load_cache()
    cache[res.fingerprint] = res
    p = paths.calibration_cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({k: v.model_dump(mode="json") for k, v in cache.items()}, indent=2), encoding="utf-8")


def cached(hw_fp: str, artifact: ModelArtifact, runtime_build: str, ctx: int) -> CalibrationResult | None:
    fp = calib_fingerprint(hw_fp, artifact, runtime_build, ctx)
    return load_cache().get(fp)


def _rss_mb(pid: int) -> float | None:
    try:
        import psutil

        p = psutil.Process(pid)
        return (p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True))) / 2**20
    except Exception:
        return None


def run_one(
    binary: Path,
    artifact: ModelArtifact,
    model_path: Path,
    ctx_size: int,
    threads: int,
    timeout_s: float = CALIBRATION_TIMEOUT_S,
    fingerprint: str = "",
) -> CalibrationResult:
    """Launch, send one bounded Vietnamese request, measure, shut down."""
    res = CalibrationResult(
        artifact_id=artifact.id,
        measured_at=datetime.now(UTC).isoformat(),
        fingerprint=fingerprint,
        settings={"ctx_size": ctx_size, "threads": threads, "parallel": 1},
    )
    cfg = LaunchConfig(
        model_path=model_path, ctx_size=ctx_size, threads=threads, parallel=1, alias=artifact.id
    )
    proc = LlamaCppProcess(binary, cfg)
    peak_rss: float | None = None
    try:
        t0 = time.monotonic()
        proc.start(ready_timeout=min(60.0, timeout_s * 0.6))
        res.load_ms = Value(value=(time.monotonic() - t0) * 1000, unit="ms", evidence=Evidence.MEASURED)
        if proc.proc:
            peak_rss = _rss_mb(proc.proc.pid) or 0.0

        client = ChatClient(proc.base_url, timeout=timeout_s)
        req = GenerationRequest(
            model=artifact.id,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": PROMPT},
            ],
            max_tokens=160,
            enable_thinking=False if artifact.thinking_capable else None,
        )
        gen = client.generate(req)
        if proc.proc:
            cur = _rss_mb(proc.proc.pid)
            if cur:
                peak_rss = max(peak_rss or 0.0, cur)
        client.close()

        if gen.error:
            res.status = "error"
            res.error = gen.error[:500]
        elif gen.cancelled:
            res.status = "timeout"
            res.error = "cancelled"
        else:
            res.status = "ok"
            if gen.ttft_ms is not None:
                res.ttft_ms = Value(value=round(gen.ttft_ms, 1), unit="ms", evidence=Evidence.MEASURED)
            t = gen.timings or {}
            if t.get("predicted_per_second"):
                res.decode_tps = Value(
                    value=round(t["predicted_per_second"], 2), unit="tok/s", evidence=Evidence.MEASURED
                )
            if t.get("prompt_per_second"):
                res.prompt_tps = Value(
                    value=round(t["prompt_per_second"], 2), unit="tok/s", evidence=Evidence.MEASURED
                )
            if peak_rss:
                res.peak_rss_mb = Value(
                    value=round(peak_rss), unit="MiB", evidence=Evidence.MEASURED,
                    note="RSS tiến trình server; không gồm cache trang hệ điều hành",
                )
    except Exception as exc:  # launch failure, OOM kill, timeout
        msg = str(exc)
        res.status = "load_failed" if "thoát sớm" in msg or "sẵn sàng" in msg else "error"
        res.error = msg[:500]
    finally:
        proc.stop()
    return res


def calibrate(
    binary: Path,
    candidates: list[tuple[ModelArtifact, Path, int, int]],
    hw_fp: str,
    timeout_s: float = CALIBRATION_TIMEOUT_S,
    use_cache: bool = True,
) -> list[CalibrationResult]:
    """Run bounded calibration over at most MAX_CANDIDATES installed models.

    candidates: [(artifact, model_path, ctx_size, threads)]
    """
    results: list[CalibrationResult] = []
    ver = probe_version(binary)
    build = ver.get("build") or ver.get("version", "unknown")
    for artifact, model_path, ctx, threads in candidates[:MAX_CANDIDATES]:
        fp = calib_fingerprint(hw_fp, artifact, build, ctx)
        if use_cache and (hit := cached(hw_fp, artifact, build, ctx)):
            results.append(hit)
            continue
        res = run_one(binary, artifact, model_path, ctx, threads, timeout_s, fingerprint=fp)
        save_result(res)
        results.append(res)
    return results
