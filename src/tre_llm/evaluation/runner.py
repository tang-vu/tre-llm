"""Tre Viet Lab evaluation runner (v0.1 core; suite content grows in M4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from tre_llm import paths
from tre_llm.cli.common import start_runtime
from tre_llm.evaluation.scorers import grade
from tre_llm.hardware import collect, fingerprint
from tre_llm.schemas import EvalItem, EvalResult, EvaluationReport, GenerationRequest


def _suite_dir(suite: str) -> Path:
    try:
        res = resources.files("tre_llm.data.evals").joinpath(suite.replace("tre-", "tre-"))
        p = Path(str(res))
        if p.is_dir():
            return p
    except (ImportError, TypeError, FileNotFoundError):
        pass
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "evals" / suite
        if cand.is_dir():
            return cand
    raise FileNotFoundError(f"Không tìm thấy suite '{suite}'")


def load_suite(suite: str = "tre-viet", split: str = "test") -> list[EvalItem]:
    d = _suite_dir(suite)
    items: list[EvalItem] = []
    for f in sorted(d.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            item = EvalItem.model_validate(json.loads(line))
            if item.split == split:
                items.append(item)
    return items


def run_suite(
    suite: str = "tre-viet",
    split: str = "test",
    model_id: str = "",
    limit: int | None = None,
    judge: str = "",
    out_dir: str | None = None,
) -> EvaluationReport:
    items = load_suite(suite, split)
    if limit:
        items = items[:limit]
    if not items:
        raise RuntimeError(f"Suite {suite} split {split} trống.")

    srv = start_runtime(model_id=model_id)
    hw = collect()
    rep = EvaluationReport(
        suite=suite,
        split=split,
        model_id=srv.effective.artifact_id,
        runtime_build="",
        hardware_fingerprint=fingerprint(hw),
        started_at=datetime.now(UTC).isoformat(),
        provenance={"judge": judge or None, "grader_note": "deterministic + rubric"},
    )
    try:
        for item in items:
            res = EvalResult(item_id=item.id)
            try:
                req = GenerationRequest(
                    model=srv.effective.artifact_id,
                    messages=(
                        [{"role": "system", "content": item.system}] if item.system else []
                    )
                    + [{"role": "user", "content": item.prompt}],
                    max_tokens=item.max_tokens,
                    enable_thinking=False,
                )
                gen = srv.client.generate(req)
                res.response = gen.text
                res.reasoning = gen.reasoning
                res.latency_ms = gen.total_ms
                if gen.error:
                    res.error = gen.error[:300]
            except Exception as exc:
                res.error = str(exc)[:300]
            if not res.error:
                rep.results.append(grade(item, res))
            else:
                rep.results.append(res)
    finally:
        srv.stop()
    rep.finished_at = datetime.now(UTC).isoformat()

    graded = [r for r in rep.results if r.score is not None]
    ungraded = [r for r in rep.results if r.score is None and not r.error]
    rep.summary = {
        "total": len(rep.results),
        "graded": len(graded),
        "ungraded": len(ungraded),
        "errors": len([r for r in rep.results if r.error]),
        "mean_score": round(sum(r.score for r in graded) / len(graded), 3) if graded else None,
        "pass_rate": round(sum(1 for r in graded if r.passed) / len(graded), 3) if graded else None,
        "by_category": _by_category(rep.results),
    }
    out_root = Path(out_dir) if out_dir else paths.eval_results_dir()
    out_root.mkdir(parents=True, exist_ok=True)
    name = f"eval-{suite}-{split}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    (out_root / f"{name}.json").write_text(rep.model_dump_json(indent=2), encoding="utf-8")
    return rep


def _by_category(results: list[EvalResult]) -> dict:
    out: dict[str, dict] = {}
    for r in results:
        cat = r.item_id.split(".")[0] if "." in r.item_id else "misc"
        d = out.setdefault(cat, {"n": 0, "graded": 0, "score_sum": 0.0})
        d["n"] += 1
        if r.score is not None:
            d["graded"] += 1
            d["score_sum"] += r.score
    for d in out.values():
        d["mean"] = round(d["score_sum"] / d["graded"], 3) if d["graded"] else None
        del d["score_sum"]
    return out
