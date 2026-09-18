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


def test_norm_sharegpt_and_prompt_response():
    from tre_llm.training.dataprep import _norm_row

    sharegpt = _norm_row(
        {"conversations": [
            {"from": "human", "value": "Hà Nội là gì?"},
            {"from": "gpt", "value": "Thủ đô của Việt Nam."},
        ]},
        "sharegpt",
    )
    assert sharegpt and sharegpt["messages"][-1]["role"] == "assistant"

    pr = _norm_row({"prompt": "1+1?", "response": "Bằng 2."}, "prompt_response")
    assert pr and pr["messages"][0]["role"] == "user"

    # sharegpt không kết bằng assistant → bỏ
    bad = _norm_row({"conversations": [{"from": "human", "value": "chỉ hỏi"}]}, "sharegpt")
    assert bad is None


def test_manifest_requires_path_xor_hf(tmp_path):
    import pytest

    from tre_llm.training.dataprep import load_manifest

    (tmp_path / "m.yaml").write_text(
        "sources:\n"
        "  - path: a.jsonl\n"
        "    hf: repo/x\n"
        "    license: CC-BY-4.0\n"
        "    provenance: test\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"path.*hf|hf.*path"):
        load_manifest(tmp_path, "m.yaml")


def test_prepare_drops_long_rows(tmp_path):
    from tre_llm.training.dataprep import prepare

    rows = [
        {"messages": [
            {"role": "user", "content": "Câu hỏi ngắn số một, đủ dài để không rỗng."},
            {"role": "assistant", "content": "Trả lời ngắn số một."},
        ]},
        {"messages": [
            {"role": "user", "content": "Câu hỏi ngắn số hai, cũng đủ dài."},
            {"role": "assistant", "content": "Trả lời ngắn số hai."},
        ]},
        {"messages": [
            {"role": "user", "content": "Câu hỏi rất dài " + "x" * 300},
            {"role": "assistant", "content": "Trả lời."},
        ]},
        {"messages": [
            {"role": "user", "content": "Câu hỏi dài khác " + "y" * 250},
            {"role": "assistant", "content": "Trả lời khác."},
        ]},
    ]
    (tmp_path / "raw.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )
    (tmp_path / "manifest.yaml").write_text(
        "sources:\n  - path: raw.jsonl\n    license: CC-BY-4.0\n    provenance: test\n",
        encoding="utf-8",
    )
    (tmp_path / "recipe.yaml").write_text(
        "base_model: x\ndata:\n  manifest: manifest.yaml\n  prepared_file: prepared.jsonl\n"
        "  train_fraction: 0.5\n  max_chars: 200\n",
        encoding="utf-8",
    )
    stats = prepare(str(tmp_path / "recipe.yaml"))
    assert stats["dropped_long"] > 0
    assert stats["total_rows"] < 4
