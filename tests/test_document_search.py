"""Real SQLite retrieval regressions; all document contents are synthetic."""

import unicodedata

import pytest

from tre_llm.documents.service import _norm, add_document, search
from tre_llm.storage.db import get_db


@pytest.mark.parametrize("query", ["điểm", "Điểm", "ĐIỂM", "diem", "DIEM", "Đà", "da", "ĐÀ NẴNG", "da nang"])
def test_vietnamese_d_stroke(tmp_path, query):
    text = "Điểm thi được đăng ở Đà Nẵng."
    path = tmp_path / "notes.md"
    path.write_text(text, encoding="utf-8")
    metadata = add_document(path)
    hits = search(query)
    assert len(hits) == 1
    assert hits[0]["document_id"] == metadata["id"]
    assert hits[0]["text"] == text
    assert hits[0]["char_offset"] == 0
    assert hits[0]["term_hits"] >= 1


def test_normalization_handles_composed_and_decomposed_vietnamese():
    text = "ĐIỂM được ĐĂNG ở Đà Nẵng"
    expected = "diem duoc dang o da nang"
    assert _norm(text) == expected
    assert _norm(unicodedata.normalize("NFD", text)) == expected


@pytest.mark.parametrize(
    "query",
    ['"diem"', '"diem', 'diem"', 'di"em', '""diem""', '"điểm"', '"Đà Nẵng"', 'điểm" thi', "diem\x00thi"],
)
def test_double_quotes_are_literal_not_fts_syntax(tmp_path, query):
    path = tmp_path / "notes.md"
    # A quote inside a whitespace term is a tokenizer separator within that
    # literal phrase: di"em matches adjacent tokens di em, not diem.
    path.write_text("Điểm thi ở Đà Nẵng. di em", encoding="utf-8")
    metadata = add_document(path)
    assert [hit["document_id"] for hit in search(query)] == [metadata["id"]]


@pytest.mark.parametrize(
    "query", ["", " ", "\t\n", "a", "đ", "\u0301", '"', '""', '"""', "***", "()", "🙂🙂", "\x00\x00"]
)
def test_empty_short_or_tokenless_input(tmp_path, query):
    path = tmp_path / "notes.md"
    path.write_text("Điểm thi ở Đà Nẵng.", encoding="utf-8")
    add_document(path)
    assert search(query) == []


@pytest.mark.parametrize("query", ["OR", "AND", "NOT", "NEAR", "(OR)", "OR*", "^OR", '"OR"'])
def test_operator_words_remain_plain_text(tmp_path, query):
    for name, text in [("operator", "OR AND NOT NEAR"), ("prefix", "ordinary nearshore")]:
        path = tmp_path / f"{name}.md"
        path.write_text(text, encoding="utf-8")
        add_document(path)
    assert [hit["name"] for hit in search(query)] == ["operator.md"]


def test_punctuation_and_quotes_do_not_inject_boolean_or_column_operators(tmp_path):
    for name, text in [
        ("alpha", "alpha"),
        ("beta", "beta"),
        ("both", "alpha beta"),
        ("literal", "text_norm alpha"),
    ]:
        path = tmp_path / f"{name}.md"
        path.write_text(text, encoding="utf-8")
        add_document(path)
    assert {h["name"] for h in search('alpha" NOT beta', k=10)} == {
        "alpha.md",
        "beta.md",
        "both.md",
        "literal.md",
    }
    assert {h["name"] for h in search('"alpha beta"', k=10)} == {
        "alpha.md",
        "beta.md",
        "both.md",
        "literal.md",
    }
    assert [h["name"] for h in search("text_norm:alpha", k=10)] == ["literal.md"]
    assert [h["name"] for h in search("alpha+beta", k=10)] == ["both.md"]


def test_unicode_whitespace_and_query_term_limit(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("Điểm thi ở Đà Nẵng. 東京大学", encoding="utf-8")
    add_document(path)
    assert search("diem\u2003nang")
    assert search("東京大学")
    assert not search(" ".join(["absent"] * 12 + ["diem"]))


def test_existing_or_bm25_and_term_hit_ranking(tmp_path):
    for name, text in [("both", "alpha beta"), ("alpha", "alpha"), ("beta", "beta " * 4), ("none", "gamma")]:
        path = tmp_path / f"{name}.md"
        path.write_text(text, encoding="utf-8")
        add_document(path)
    # Use the old, intended SQL for this quote-free ASCII query as the oracle.
    rows = (
        get_db()
        .execute(
            "SELECT c.id, c.text, bm25(chunks_fts) AS score FROM chunks_fts "
            "JOIN chunks c ON c.id=chunks_fts.chunk_id "
            "WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?",
            ('"alpha" OR "beta"', 8),
        )
        .fetchall()
    )
    expected = sorted(
        rows, key=lambda row: (-sum(term in row["text"] for term in {"alpha", "beta"}), row["score"])
    )
    hits = search("alpha beta")
    assert [h["id"] for h in hits] == [row["id"] for row in expected]
    assert [h["score"] for h in hits] == [row["score"] for row in expected]
    assert hits[0]["name"] == "both.md" and hits[0]["term_hits"] == 2
    assert {h["name"] for h in hits} == {"both.md", "alpha.md", "beta.md"}
