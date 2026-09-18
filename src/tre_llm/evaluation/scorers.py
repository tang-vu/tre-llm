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
    else:  # rubric — needs an explicit judge model; else stays ungraded
        if judge_client is not None:
            return _grade_rubric(item, res, judge_client, judge_model, g)
        res.grader = "rubric-ungraded"
        res.score = None
        res.passed = None
        res.detail = g.get("rubric", "")
        return res

    # `forbid`: phrases that must NOT appear (injection strings, refusals).
    # Applies to every auto-graded kind; overrides the computed result.
    forbidden = [p for p in g.get("forbid", []) if _fold(str(p)) in _fold(text)]
    if forbidden:
        res.score, res.passed = 0.0, False
        res.detail = (res.detail + " | " if res.detail else "") + f"forbidden: {forbidden}"
    return res


_JUDGE_PROMPT = """Bạn là giám khảo chấm điểm câu trả lời của một model AI theo tiêu chí cho trước.

Câu hỏi/đề bài:
{prompt}

Câu trả lời của model:
{response}

Tiêu chí chấm:
{rubric}

Chỉ trả lời đúng một JSON object không giải thích: {{"score": X, "nhan_xet": "..."}}
với X ∈ {{0, 1, 2}}: 0 = không đạt, 1 = đạt một phần, 2 = đạt đầy đủ."""


def _grade_rubric(item: EvalItem, res: EvalResult, judge_client, judge_model: str, g: dict) -> EvalResult:
    """LLM-as-judge for rubric items. Honest fallback: judge lỗi → ungraded."""
    from tre_llm.schemas import GenerationRequest

    prompt = _JUDGE_PROMPT.format(
        prompt=item.prompt[:2000],
        response=(res.response or "")[:3000],
        rubric=g.get("rubric", ""),
    )
    try:
        gen = judge_client.generate(GenerationRequest(
            model=judge_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=160,
            temperature=0.0,
            enable_thinking=False,
        ))
    except Exception as exc:
        res.grader = "rubric-ungraded"
        res.detail = f"judge lỗi: {exc}"[:200]
        return res
    if gen.error or not gen.text.strip():
        res.grader = "rubric-ungraded"
        res.detail = f"judge không trả lời: {gen.error or 'empty'}"[:200]
        return res
    # Parse: full JSON trước; nếu output bị cắt (max_tokens) thì bắt field
    # "score" đầu tiên — model nhỏ thường viết nhan_xet dài làm JSON cụt đuôi.
    verdict: dict = {}
    raw = -1
    m = re.search(r"\{.*\}", gen.text, re.S)
    if m:
        try:
            verdict = json.loads(m.group(0))
            raw = int(verdict.get("score", -1))
        except (json.JSONDecodeError, TypeError, ValueError):
            raw = -1
    if raw not in (0, 1, 2):
        ms = re.search(r'"score"\s*:\s*([0-2])', gen.text)
        if ms:
            raw = int(ms.group(1))
    if raw not in (0, 1, 2):
        res.grader = "rubric-ungraded"
        res.detail = f"judge output không parse được: {gen.text[:120]}"
        return res
    res.grader = f"judge:{judge_model}"
    res.score = raw / 2.0
    res.passed = raw >= 1
    res.detail = f"judge={raw}/2 — {str(verdict.get('nhan_xet', ''))[:120]}"
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
