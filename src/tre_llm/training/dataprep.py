"""Tre Adapt data preparation — reproducible, validated, leakage-checked.

prepare(): manifest -> normalized JSONL (dedup, deterministic split, hashes).
validate(): schema + quality + leakage vs eval suite. A prepared file that
fails validation must never reach the trainer silently.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

REQUIRED_SOURCE_FIELDS = {"path", "license", "provenance"}

_VI_CHARS = re.compile(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.I)


def _fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _flatten(messages: list[dict[str, str]]) -> str:
    """Deterministic plain-text rendering for the SFT smoke pipeline.

    NOTE: this is a simplified format for the pipeline test. A quality run
    should render via the base model's chat template instead.
    """
    parts = []
    for m in messages:
        role = {"system": "Hệ thống", "user": "Người dùng", "assistant": "Trợ lý"}.get(
            m.get("role", ""), m.get("role", "?")
        )
        parts.append(f"{role}: {m.get('content', '').strip()}")
    return "\n".join(parts)


def _norm_row(row: dict[str, Any], fmt: str) -> dict[str, Any] | None:
    """Normalize a raw source row to {text, messages}; None if invalid."""
    if fmt == "messages" or "messages" in row:
        msgs = row.get("messages") or []
        if not msgs or msgs[-1].get("role") != "assistant":
            return None
        return {"text": _flatten(msgs), "messages": msgs}
    if "instruction" in row and "output" in row:
        msgs = [
            {"role": "user", "content": str(row["instruction"]).strip()},
            {"role": "assistant", "content": str(row["output"]).strip()},
        ]
        return {"text": _flatten(msgs), "messages": msgs}
    if "text" in row and str(row["text"]).strip():
        return {"text": str(row["text"]).strip()}
    return None


def load_manifest(recipe_dir: Path, manifest_name: str) -> dict[str, Any]:
    mpath = recipe_dir / manifest_name
    if not mpath.is_file():
        raise FileNotFoundError(f"Không tìm thấy manifest: {mpath}")
    m = yaml.safe_load(mpath.read_text(encoding="utf-8")) or {}
    if not m.get("sources"):
        raise ValueError("Manifest không có 'sources'.")
    for s in m["sources"]:
        missing = REQUIRED_SOURCE_FIELDS - set(s)
        if missing:
            raise ValueError(f"Source thiếu trường {missing}: {s}")
        if s.get("license", "").upper() in ("", "UNKNOWN"):
            raise ValueError(f"Source thiếu license rõ ràng: {s.get('path')}")
    return m


def prepare(recipe_path: str) -> dict[str, Any]:
    from tre_llm.training.run import _load_recipe

    recipe, p = _load_recipe(recipe_path)
    data = recipe.get("data", {})
    manifest = load_manifest(p.parent, data.get("manifest", "manifest.yaml"))

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats = {"sources": [], "dropped_invalid": 0, "dropped_dup": 0}
    for src in manifest["sources"]:
        f = p.parent / src["path"]
        if not f.is_file():
            raise FileNotFoundError(f"Nguồn dữ liệu không tồn tại: {f}")
        n_src = 0
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                stats["dropped_invalid"] += 1
                continue
            norm = _norm_row(raw, src.get("format", ""))
            if norm is None or len(norm["text"]) < 20:
                stats["dropped_invalid"] += 1
                continue
            h = hashlib.sha256(_fold(norm["text"]).encode()).hexdigest()
            if h in seen:
                stats["dropped_dup"] += 1
                continue
            seen.add(h)
            norm["source"] = src["path"]
            norm["license"] = src["license"]
            rows.append(norm)
            n_src += 1
        stats["sources"].append({"path": src["path"], "rows": n_src, "license": src["license"], "provenance": src["provenance"]})

    rng = random.Random(int(recipe.get("seed", 42)))
    rng.shuffle(rows)
    frac = float(data.get("train_fraction", 0.9))
    cut = max(1, int(len(rows) * frac)) if rows else 0
    out_name = data.get("prepared_file", "prepared.jsonl")
    out = p.parent / out_name
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats.update(
        {
            "total_rows": len(rows),
            "train_rows": cut,
            "eval_rows": len(rows) - cut,
            "prepared_file": str(out),
            "prepared_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "seed": int(recipe.get("seed", 42)),
            "note": "format text đơn giản hóa cho pipeline test — chưa phải chat template của base model",
        }
    )
    (p.parent / "prepared.stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def validate(prepared_file: str | Path, check_leakage: bool = True) -> dict[str, Any]:
    """Validate a prepared JSONL. Returns {ok, issues[], stats}."""
    f = Path(prepared_file)
    issues: list[str] = []
    if not f.is_file():
        return {"ok": False, "issues": [f"Không tìm thấy file: {f}"], "stats": {}}

    rows = []
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            issues.append(f"dòng {i + 1}: JSON lỗi")

    vi_rows = sum(1 for r in rows if _VI_CHARS.search(r.get("text", "")))
    short = sum(1 for r in rows if len(r.get("text", "")) < 20)
    if short:
        issues.append(f"{short} dòng quá ngắn (<20 ký tự)")
    if rows and vi_rows / len(rows) < 0.5:
        issues.append(f"Chỉ {vi_rows}/{len(rows)} dòng có ký tự tiếng Việt — kiểm tra lại ngôn ngữ dữ liệu")

    if check_leakage:
        try:
            from tre_llm.evaluation.runner import load_suite

            eval_prompts = {
                _fold(it.prompt) for split in ("dev", "test") for it in load_suite("tre-viet", split)
            }
        except Exception as exc:  # suite unavailable => warn, don't pass silently
            issues.append(f"Không kiểm tra được leakage với eval suite: {exc}")
            eval_prompts = set()
        for i, r in enumerate(rows):
            t = _fold(r.get("text", ""))
            for ep in eval_prompts:
                if len(ep) > 30 and ep in t:
                    issues.append(f"dòng {i + 1}: TRÙNG prompt eval suite (leakage)")
                    break

    return {
        "ok": not issues,
        "issues": issues,
        "stats": {"rows": len(rows), "vi_rows": vi_rows, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()},
    }
