"""Deterministic scorers for Tre Viet items + rubric plumbing.

grading.kind values:
- exact:       response stripped == expected string
- contains:    all expected substrings present (case/accent-insensitive)
- regex:       expected pattern matches response
- json_schema: response parses as JSON and contains required fields/values
- numeric:     expected number appears in response
- rubric:      NOT auto-scored unless an explicit judge model is configured;
               raw answer preserved, score stays None (ungraded).
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from tre_llm.schemas import EvalItem, EvalResult


def _fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def grade(item: EvalItem, res: EvalResult, judge_client=None, judge_model: str = "") -> EvalResult:
    g = item.grading or {}
    kind = g.get("kind", "rubric")
    text = res.response or ""

    if kind == "exact":
        ok = text.strip() == str(item.expected).strip()
        res.score, res.passed = float(ok), ok
    elif kind == "contains":
        exp = item.expected if isinstance(item.expected, list) else [item.expected]
        hits = [e for e in exp if _fold(str(e)) in _fold(text)]
        res.score = len(hits) / max(len(exp), 1)
        res.passed = res.score >= float(g.get("threshold", 1.0))
        res.detail = f"contains {len(hits)}/{len(exp)}"
    elif kind == "regex":
        ok = bool(re.search(str(item.expected), text, re.S))
        res.score, res.passed = float(ok), ok
    elif kind == "numeric":
        nums = re.findall(r"-?\d+(?:[.,]\d+)?", text)
        want = str(item.expected).replace(",", ".")
        ok = any(n.replace(",", ".") == want for n in nums)
        res.score, res.passed = float(ok), ok
        res.detail = f"found {nums[:8]}, want {want}"
    elif kind == "json_schema":
        res.score, res.passed, res.detail = _grade_json(text, item.expected or {})
    elif kind == "citation_exists":
        # citations must reference real chunk ids supplied in the prompt context
        valid = set(g.get("valid_ids") or [])
        cited = set(re.findall(r"\[([^\]]+)\]", text))
        if g.get("expect_unanswerable"):
            ok = not cited or "không" in _fold(text)
            res.score, res.passed = float(ok), ok
        else:
            ok = bool(cited & valid) and not (cited - valid)
            res.score, res.passed = float(ok), ok
            res.detail = f"cited={sorted(cited)} valid={sorted(valid)}"
    elif kind == "refusal":
        # should NOT refuse; a refusal phrase fails
        refused = any(p in _fold(text) for p in g.get("refusal_phrases", ["xin lỗi, tôi không thể", "tôi không thể"]))
        res.score, res.passed = 0.0 if refused else 1.0, not refused
    else:  # rubric — never auto-graded without an explicit judge
        res.grader = "rubric-ungraded"
        res.score = None
        res.passed = None
        res.detail = g.get("rubric", "")
    return res


def _grade_json(text: str, expected: dict[str, Any]) -> tuple[float, bool, str]:
    # Extract first JSON object if wrapped in prose/code fence.
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return 0.0, False, "không tìm thấy JSON"
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return 0.0, False, f"JSON lỗi: {e}"
    if not isinstance(data, dict):
        return 0.0, False, "không phải JSON object"
    need = expected.get("fields", {})
    missing = [k for k in need if k not in data]
    wrong = [k for k, v in need.items() if k in data and _fold(str(data[k])) != _fold(str(v))]
    score = 1.0 - (len(missing) + len(wrong)) / max(len(need), 1)
    return score, not missing and not wrong, f"missing={missing} wrong={wrong}"
