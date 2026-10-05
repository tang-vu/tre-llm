-- Frozen schema from c4ccee5 (before Vietnamese đ search migration).

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


    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        chunk_id UNINDEXED,
        text_norm,
        tokenize = 'unicode61 remove_diacritics 2'
    );


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

PRAGMA user_version = 4;
