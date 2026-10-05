"""Upgrade actual schema-4 SQLite fixtures without source files or reimporting."""

import hashlib
import sqlite3
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tre_llm.documents.service import _norm, add_document, search
from tre_llm.storage import db as dbmod
from tre_llm.storage.db import DB


def _old_norm(text):
    # Frozen pre-fix normalization, deliberately not the production helper.
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()


def _snapshot(conn):
    tables = ("settings", "conversations", "messages", "runs", "documents", "sqlite_sequence", "user_extra")
    result = {table: conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in tables}
    result["chunks"] = conn.execute(
        "SELECT id, document_id, seq, text, char_offset, char_length, token_est FROM chunks ORDER BY rowid"
    ).fetchall()
    return result


@pytest.fixture()
def old_database(tmp_path):
    path = tmp_path / "old.sqlite"
    source = tmp_path / "notes.md"
    text = "Điểm thi được đăng ở Đà Nẵng.\n\nĐƯỜNG đi đến trường."
    source.write_text(text, encoding="utf-8")
    doc_id = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:12]
    conn = sqlite3.connect(path)
    try:
        conn.executescript((Path(__file__).parent / "fixtures" / "documents-v4.sql").read_text())
        conn.execute(
            "INSERT INTO settings VALUES (?, ?)", ("preferences", '{"language":"vi","nested":[1,2]}')
        )
        conn.execute(
            "INSERT INTO conversations VALUES ('conv', 'Tên hội thoại', 'model', 'created', 'updated', 'summary', 2)"
        )
        conn.execute(
            "INSERT INTO messages VALUES (42, 'conv', 0, 'user', 'Nội dung', 'reasoning', 7, 'created')"
        )
        conn.execute(
            "INSERT INTO runs VALUES ('run', 'eval', 'done', 'model', '{\"score\":1}', '/report', 'created', 'finished')"
        )
        conn.execute("CREATE TABLE user_extra (key TEXT, value BLOB)")
        conn.execute("INSERT INTO user_extra VALUES ('extension', X'00FF')")
        for identifier, filename, content, status in [
            (doc_id, source, text, "indexed"),
            ("missing", tmp_path / "gone.md", "Hà Nội là thủ đô. ĐIỆN BIÊN", "indexed"),
            ("failed", tmp_path / "failed.md", "", "failed"),
        ]:
            conn.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, 'created', 'updated')",
                (
                    identifier,
                    filename.name,
                    str(filename),
                    hashlib.sha256(content.encode()).hexdigest(),
                    len(content.encode()),
                    status,
                    "saved error" if status == "failed" else "",
                ),
            )
            for seq, piece in enumerate(content.split("\n\n") if content else []):
                offset = content.index(piece)
                cid = f"{identifier}:{seq}"
                conn.execute(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (cid, identifier, seq, piece, _old_norm(piece), offset, len(piece), len(piece) // 4),
                )
                conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, text_norm) VALUES (?, ?)", (cid, _old_norm(piece))
                )
        conn.commit()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert not conn.execute("SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH 'diem'").fetchall()
        assert conn.execute("SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH 'điem'").fetchall()
        snapshot = _snapshot(conn)
    finally:
        conn.close()
    return path, source, snapshot


def _assert_upgraded(path, before):
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert _snapshot(conn) == before
        chunks = conn.execute("SELECT id, text, text_norm FROM chunks ORDER BY id").fetchall()
        assert all(norm == _norm(original) for _, original, norm in chunks)
        assert conn.execute("SELECT chunk_id, text_norm FROM chunks_fts ORDER BY chunk_id").fetchall() == [
            (cid, norm) for cid, _, norm in chunks
        ]
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('integrity-check')")
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_upgrade_preserves_data_without_source_files_and_reopens(old_database):
    path, source, before = old_database
    source.unlink()
    db = DB(path)
    try:
        for query in ("diem", "da", "duong", "dien", "ĐIỂM", '"diem'):
            assert search(query, db=db)
        db.migrate()  # Explicit rerun and reopening must both be harmless.
    finally:
        db.close()
    _assert_upgraded(path, before)
    db = DB(path)
    try:
        assert search("diem", db=db)
        assert db.schema_version == 5
    finally:
        db.close()
    _assert_upgraded(path, before)


def test_unchanged_reimport_does_not_skip_index_upgrade(old_database):
    path, source, before = old_database
    db = DB(path)
    try:
        result = add_document(source, db=db)
        assert result["status"] == "unchanged" and result["chunks"] == -1
        hits = search("diem", db=db)
        assert hits[0]["document_id"] == result["id"]
        assert hits[0]["text"] == "Điểm thi được đăng ở Đà Nẵng."
        assert hits[0]["char_offset"] == 0
    finally:
        db.close()
    _assert_upgraded(path, before)


@pytest.mark.parametrize("failure", ["update", "delete", "insert", "version", "commit"])
def test_failed_upgrade_rolls_back_data_index_and_version(old_database, monkeypatch, failure):
    path, _, before = old_database
    connect = sqlite3.connect
    with connect(path) as conn:
        old_chunks = conn.execute("SELECT * FROM chunks ORDER BY id").fetchall()
        old_fts = conn.execute("SELECT rowid, * FROM chunks_fts ORDER BY rowid").fetchall()

    def authorizer(action, arg1, arg2, _database, _trigger):
        denied = {
            "update": action == sqlite3.SQLITE_UPDATE and arg1 == "chunks",
            "delete": action == sqlite3.SQLITE_DELETE and arg1 == "chunks_fts",
            "insert": action == sqlite3.SQLITE_INSERT and arg1 == "chunks_fts",
            "version": action == sqlite3.SQLITE_PRAGMA and arg1 == "user_version" and arg2 == "5",
            "commit": action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT",
        }
        return sqlite3.SQLITE_DENY if denied[failure] else sqlite3.SQLITE_OK

    def failing_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_authorizer(authorizer)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(dbmod.sqlite3, "connect", failing_connect)
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            DB(path)
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")  # Failed constructor released its lock.
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert _snapshot(conn) == before
        assert conn.execute("SELECT * FROM chunks ORDER BY id").fetchall() == old_chunks
        assert conn.execute("SELECT rowid, * FROM chunks_fts ORDER BY rowid").fetchall() == old_fts
        assert conn.execute("SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH 'điem'").fetchall()
        conn.rollback()
    DB(path).close()  # A later startup can retry successfully.
    _assert_upgraded(path, before)


def test_concurrent_openers_upgrade_once(old_database):
    path, _, before = old_database

    def open_and_search(_):
        db = DB(path)
        try:
            return db.schema_version, len(search("diem", db=db))
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(open_and_search, range(4))) == [(5, 1)] * 4
    _assert_upgraded(path, before)


def test_current_database_open_and_migrate_need_no_writer_lock(tmp_path, monkeypatch):
    path = tmp_path / "current.sqlite"
    DB(path).close()
    connect = sqlite3.connect

    def nonblocking_connect(*args, **kwargs):
        kwargs["timeout"] = 0
        return connect(*args, **kwargs)

    with connect(path) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with monkeypatch.context() as patch:
            patch.setattr(dbmod.sqlite3, "connect", nonblocking_connect)
            db = DB(path)
            try:
                db.migrate()
                assert db.schema_version == 5
            finally:
                db.close()
        writer.rollback()
