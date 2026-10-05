"""Deterministic startup locking/error tests against real SQLite connections."""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tre_llm.storage import db as dbmod
from tre_llm.storage.db import DB


@pytest.fixture()
def rollback_database(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript((Path(__file__).parent / "fixtures" / "documents-v4.sql").read_text())
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    return path


def test_wal_initialization_retries_real_lock_then_preserves_timeout(rollback_database, monkeypatch):
    retry_seen = threading.Event()
    released = threading.Event()
    real_sleep = dbmod.sleep

    def synchronized_sleep(delay):
        retry_seen.set()
        assert released.wait(timeout=5)
        real_sleep(delay)

    monkeypatch.setattr(dbmod, "sleep", synchronized_sleep)
    with sqlite3.connect(rollback_database) as writer, ThreadPoolExecutor(max_workers=1) as pool:
        writer.execute("BEGIN IMMEDIATE")
        opening = pool.submit(DB, rollback_database)
        try:
            assert retry_seen.wait(
                timeout=5
            ), "WAL initialization must encounter and retry the real writer lock"
            assert writer.execute("PRAGMA user_version").fetchone()[0] == 4
        finally:
            writer.rollback()
            released.set()
        db = opening.result(timeout=5)
        try:
            assert db.schema_version == 5
            assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        finally:
            db.close()


def test_wal_lock_deadline_is_bounded_and_closes_connection(rollback_database, monkeypatch):
    connect = sqlite3.connect
    connections = []
    wal_attempts = []

    def tracked_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        connections.append(conn)
        conn.set_trace_callback(
            lambda sql: wal_attempts.append(sql) if sql == "PRAGMA journal_mode = WAL" else None
        )
        return conn

    now = [0.0]
    monkeypatch.setattr(dbmod, "monotonic", lambda: now[0])
    monkeypatch.setattr(dbmod, "sleep", lambda delay: now.__setitem__(0, now[0] + delay))
    monkeypatch.setattr(dbmod, "_WAL_INIT_TIMEOUT", 0.1)
    monkeypatch.setattr(dbmod.sqlite3, "connect", tracked_connect)
    with connect(rollback_database) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError) as failure:
            DB(rollback_database)
        assert failure.value.sqlite_errorcode & 0xFF == sqlite3.SQLITE_BUSY
        assert now[0] == pytest.approx(0.1)
        assert len(wal_attempts) == 3
        assert writer.execute("PRAGMA user_version").fetchone()[0] == 4
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connections[0].execute("SELECT 1")
        writer.rollback()
    # The temporary contention has ended; a new connection can initialize.
    db = DB(rollback_database)
    assert db.schema_version == 5
    db.close()


@pytest.mark.parametrize("pragma", ["foreign_keys", "journal_mode"])
def test_non_lock_initialization_error_propagates_immediately_and_closes(
    rollback_database, monkeypatch, pragma
):
    connect = sqlite3.connect
    connections = []
    attempted = []

    def authorizer(action, arg1, _arg2, _database, _trigger):
        if action == sqlite3.SQLITE_PRAGMA and arg1 == pragma:
            attempted.append(arg1)
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def denied_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        connections.append(conn)
        conn.set_authorizer(authorizer)
        return conn

    def no_retry(_):
        pytest.fail("Non-lock errors must not be retried")

    monkeypatch.setattr(dbmod.sqlite3, "connect", denied_connect)
    monkeypatch.setattr(dbmod, "sleep", no_retry)
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        DB(rollback_database)
    assert attempted == [pragma]
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")
    with connect(rollback_database) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
