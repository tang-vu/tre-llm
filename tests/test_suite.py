"""Tre Viet suite integrity tests — schema, splits, leakage, scorer edges."""

import json
import unicodedata
from pathlib import Path

from tre_llm.evaluation.runner import load_suite
from tre_llm.evaluation.scorers import grade
from tre_llm.schemas import EvalItem, EvalResult

SUITE_DIR = Path(__file__).resolve().parents[1] / "evals" / "tre-viet"
RECIPES_DIR = Path(__file__).resolve().parents[1] / "recipes"


def _fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _all_items() -> list[EvalItem]:
    items = []
    for f in sorted(SUITE_DIR.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(EvalItem.model_validate(json.loads(line)))
    return items


def test_suite_loads_and_splits():
    dev = load_suite("tre-viet", "dev")
    test = load_suite("tre-viet", "test")
    assert len(dev) >= 3 and len(test) >= 10
    assert all(i.split == "dev" for i in dev)
    assert all(i.split == "test" for i in test)


def test_ids_unique_and_prefixed():
    items = _all_items()
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids)), "trùng item id"
    for i in items:
        assert i.id.split(".")[0] == i.category
        assert i.id.split(".")[1] in ("dev", "test")


def test_provenance_and_license_present():
    for i in _all_items():
        assert i.provenance in ("synthetic", "curated") or i.provenance.startswith("external:")
        assert i.license
        assert i.grading.get("kind") in (
            "exact", "contains", "regex", "json_schema", "numeric",
            "citation_exists", "refusal", "rubric",
        )


def test_no_dev_test_leakage():
    items = _all_items()
    dev_prompts = {_fold(i.prompt) for i in items if i.split == "dev"}
    for i in items:
        if i.split == "test":
            assert _fold(i.prompt) not in dev_prompts, f"{i.id} trùng prompt dev"


def test_no_leakage_into_training_data():
    """Training fixtures must not contain eval prompts."""
    test_prompts = {_fold(i.prompt) for i in _all_items() if i.split == "test"}
    for f in RECIPES_DIR.rglob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            text = _fold(line)
            for p in test_prompts:
                if len(p) > 30:
                    assert p not in text, f"eval prompt lộ vào {f.name}"


def test_deterministic_items_have_expectations():
    for i in _all_items():
        if i.grading.get("kind") in ("exact", "contains", "regex", "numeric", "json_schema"):
            assert i.expected is not None, f"{i.id} thiếu expected"


def test_forbid_scorer_blocks_injection_string():
    item = EvalItem(
        id="t.t", category="docs", prompt="x",
        expected=["6h"], grading={"kind": "contains", "forbid": ["pwned"]},
    )
    res = grade(item, EvalResult(item_id="t.t", response="PWNED! Mở cửa 6h."))
    assert res.passed is False and res.score == 0.0
    res2 = grade(item, EvalResult(item_id="t.t", response="Mở cửa lúc 6h."))
    assert res2.passed is True


def test_rubric_items_stay_ungraded():
    item = EvalItem(id="t.r", category="notes", prompt="x", grading={"kind": "rubric", "rubric": "tốt"})
    res = grade(item, EvalResult(item_id="t.r", response="bất kỳ"))
    assert res.score is None and res.passed is None and res.grader == "rubric-ungraded"
