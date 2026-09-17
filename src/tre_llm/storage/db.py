"""SQLite storage: settings, conversations, documents, chunks, eval runs.

Migrations are explicit, ordered, and tested. The DB never stores model
weights — see registry/store.py for the artifact index.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tre_llm import paths

MIGRATIONS: list[str] = [
    # 1 — settings + conversations + messages
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL DEFAULT '',
        model_id TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        summarized_up_to INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        seq INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        reasoning TEXT NOT NULL DEFAULT '',
        tokens INTEGER,
        created_at TEXT NOT NULL,
        UNIQUE(conversation_id, seq)
    );
    CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, seq);
    """,
    # 2 — documents + chunks (FTS5 in migration 3)
    """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        source_path TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'indexed',  -- indexing | indexed | failed
        error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        seq INTEGER NOT NULL,
        text TEXT NOT NULL,
        text_norm TEXT NOT NULL,
        char_offset INTEGER NOT NULL,
        char_length INTEGER NOT NULL,
        token_est INTEGER NOT NULL DEFAULT 0,
        UNIQUE(document_id, seq)
    );
    CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id, seq);
    """,
    # 3 — FTS5 over normalized text (unicode61 keeps accents in `text`;
    # text_norm stores a folded copy for accentless recall).
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        chunk_id UNINDEXED,
        text_norm,
        tokenize = 'unicode61 remove_diacritics 2'
    );
    """,
    # 4 — eval + perf run registry
    """
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,            -- eval | bench | calibrate | train
        status TEXT NOT NULL,
        model_id TEXT NOT NULL DEFAULT '',
        payload TEXT NOT NULL DEFAULT '{}',
        report_path TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        finished_at TEXT NOT NULL DEFAULT ''
    );
    """,
]

_SCHEMA_VERSION = len(MIGRATIONS)


class DB:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self.migrate()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def migrate(self) -> None:
        with self._lock:
            cur = self._conn.execute("PRAGMA user_version")
            version = cur.fetchone()[0]
            for i, sql in enumerate(MIGRATIONS, start=1):
                if i > version:
                    self._conn.executescript(sql)
                    self._conn.execute(f"PRAGMA user_version = {i}")
            self._conn.commit()

    @property
    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    # ------------------------------------------------------------ settings

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def set_setting(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        self.commit()

    # -------------------------------------------------------- conversations

    def create_conversation(self, conv_id: str, model_id: str = "", title: str = "") -> None:
        now = datetime.now(UTC).isoformat()
        self.execute(
            "INSERT INTO conversations(id, title, model_id, created_at, updated_at) VALUES(?,?,?,?,?)",
            (conv_id, title, model_id, now, now),
        )
        self.commit()

    def add_message(self, conv_id: str, role: str, content: str, reasoning: str = "", tokens: int | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        row = self.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 AS s FROM messages WHERE conversation_id=?",
            (conv_id,),
        ).fetchone()
        self.execute(
            "INSERT INTO messages(conversation_id, seq, role, content, reasoning, tokens, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (conv_id, row["s"], role, content, reasoning, tokens, now),
        )
        self.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id))
        self.commit()

    def messages(self, conv_id: str) -> list[dict[str, Any]]:
        rows = self.execute(
            "SELECT seq, role, content, reasoning, tokens, created_at FROM messages "
            "WHERE conversation_id=? ORDER BY seq",
            (conv_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.execute(
            "SELECT id, title, model_id, created_at, updated_at FROM conversations "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def rename_conversation(self, conv_id: str, title: str) -> None:
        self.execute("UPDATE conversations SET title=? WHERE id=?", (title, conv_id))
        self.commit()

    def delete_conversation(self, conv_id: str) -> None:
        self.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
        self.commit()

    # ------------------------------------------------------------- runs

    def add_run(self, run_id: str, kind: str, model_id: str, status: str = "running", payload: dict | None = None) -> None:
        self.execute(
            "INSERT INTO runs(id, kind, status, model_id, payload, created_at) VALUES(?,?,?,?,?,?)",
            (run_id, kind, status, model_id, json.dumps(payload or {}), datetime.now(UTC).isoformat()),
        )
        self.commit()

    def finish_run(self, run_id: str, status: str, report_path: str = "") -> None:
        self.execute(
            "UPDATE runs SET status=?, report_path=?, finished_at=? WHERE id=?",
            (status, report_path, datetime.now(UTC).isoformat(), run_id),
        )
        self.commit()


_default: DB | None = None
_default_lock = threading.Lock()


def get_db() -> DB:
    global _default
    with _default_lock:
        if _default is None:
            _default = DB()
        return _default


def reset_default() -> None:
    global _default
    with _default_lock:
        if _default is not None:
            _default.close()
            _default = None
