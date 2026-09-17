"""Tre Adapt dataprep tests — prepare determinism, validation, leakage."""

import json
from pathlib import Path

from tre_llm.training.dataprep import prepare, validate

RECIPE = "recipes/tiny-vi-notes/recipe.yaml"
RECIPE_DIR = Path(__file__).resolve().parents[1] / "recipes" / "tiny-vi-notes"


def test_prepare_deterministic(tmp_path):
    # Prepare twice into the same recipe dir — output must be byte-identical.
    stats1 = prepare(RECIPE)
    sha1 = stats1["prepared_sha256"]
    stats2 = prepare(RECIPE)
    assert stats1["prepared_sha256"] == stats2["prepared_sha256"] == sha1
    assert stats1["total_rows"] == 16
    assert stats1["train_rows"] + stats1["eval_rows"] == 16


def test_prepare_rows_wellformed(tmp_path):
    prepare(RECIPE)
    out = RECIPE_DIR / "prepared.jsonl"
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in rows:
        assert r["text"] and "Người dùng:" in r["text"] and "Trợ lý:" in r["text"]
        assert r["messages"][-1]["role"] == "assistant"
        assert r["license"] == "CC-BY-4.0"
    out.unlink()
    (RECIPE_DIR / "prepared.stats.json").unlink(missing_ok=True)


def test_validate_accepts_prepared(tmp_path):
    prepare(RECIPE)
    rep = validate(RECIPE_DIR / "prepared.jsonl")
    assert rep["ok"], rep["issues"]
    assert rep["stats"]["rows"] == 16
    (RECIPE_DIR / "prepared.jsonl").unlink()
    (RECIPE_DIR / "prepared.stats.json").unlink(missing_ok=True)


def test_validate_catches_leakage(tmp_path):
    # Inject an eval-suite prompt into training data — must be flagged.
    bad = tmp_path / "bad.jsonl"
    eval_prompt = "Một năm có bao nhiêu tuần? Trả lời chỉ bằng một con số."
    bad.write_text(
        json.dumps({"text": f"Người dùng: {eval_prompt}\nTrợ lý: 52 tuần nhé"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    rep = validate(bad)
    assert not rep["ok"]
    assert any("leakage" in i or "TRÙNG" in i for i in rep["issues"])


def test_validate_flags_non_vietnamese(tmp_path):
    f = tmp_path / "en.jsonl"
    f.write_text(
        json.dumps({"text": "User: explain photosynthesis briefly\nAssistant: Plants convert light."})
        + "\n",
        encoding="utf-8",
    )
    rep = validate(f, check_leakage=False)
    assert not rep["ok"]
    assert any("tiếng Việt" in i for i in rep["issues"])
