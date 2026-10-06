# TreLLM — Architecture (v0.1)

## Tổng quan

```
tre CLI ─┐                          ┌─ llama-server (owned subprocess)
         ├─ tre_llm core library ───┤   FastAPI local API ── apps/web (static, same-origin)
humans ──┘   (importable)           └─ external OpenAI-compatible server (attach mode)
                        │
                        ├─ hardware/    probes: cpu/mem/gpu/disk/os (timeout, structured errors)
                        ├─ planner/     memory estimate, selection, calibration, recovery
                        ├─ registry/    curated artifacts, verified downloads, local import
                        ├─ runtimes/    versioned launch adapters (llama.cpp first)
                        ├─ inference/   HTTPX client: stream, cancel, tokens, health
                        ├─ documents/   ingest .txt/.md/.pdf, FTS5 index, citations
                        ├─ evaluation/  Tre Viet suites, deterministic+ rubric scorers, reports
                        ├─ training/    data prep, SFT/LoRA pilot, export (optional deps)
                        ├─ server/      FastAPI app: /v1/* + /api/* + static UI
                        └─ storage/     SQLite + explicit migrations
```

## Ranh giới sở hữu

- Control plane (Python) KHÔNG phụ thuộc torch/transformers. Chat install không kéo theo stack training.
- llama.cpp chạy như **supervised subprocess** do Tre sở hữu: start → readiness → stream → cancel → shutdown; cũng hỗ trợ attach vào server ngoài khi user cấu hình rõ.
- UI (React/Vite build tĩnh) được FastAPI phục vụ same-origin, gọi `/api/*` và `/v1/*`; UI không chứa selection logic.
- SQLite lưu settings, conversations, documents, eval results. Migration explicit + tested.

## Key decisions

- Runtime adapter giao tiếp qua OpenAI-compatible HTTP của llama-server; probe `--version`/`--list-devices` để phát hiện capability (xem ADR-001).
- Registry integrity: SHA-256 lấy từ HF tree API `lfs.oid` (x-linked-etag không tin cậy — đo thật 2026-09-17).
- 3 goal: `light` (Nhẹ máy), `balanced` (Cân bằng), `quality` (Ưu tiên chất lượng) — deterministic tie-break: model_id asc.
- Recovery chain tối đa 2 lần: giảm concurrency/batch → giảm ctx (có disclose) → đổi offload → đổi artifact nhỏ hơn đã cài → dừng với giải thích.

## Quy ước

- Human output mặc định tiếng Việt; JSON/identifier ổn định, không dịch.
- Mọi schema có `schema_version`. Timestamp ISO-8601 UTC, units rõ ràng.
- Không ghi path user/secret vào log public; export report mặc định đã redact.


## Document search and index upgrades

- `tre ask`, `/api/ask` and the document service treat queries as plain text, not an advanced FTS5 expression. After case/accent folding (including `đ`/`Đ` → `d`), whitespace-separated terms of at least two characters are quoted literally; up to 12 terms are joined with OR. Double quotes are escaped, and NUL is treated as a tokenizer separator inside a term. Operator-like words and punctuation are passed to SQLite's tokenizer as text, not executed as Boolean, prefix or column-filter syntax.
- Retrieval keeps the existing BM25 candidate selection and distinct-term-hit reranking. Original chunk text and citation offsets retain their accents and case.
- Schema 5 folds `đ`/`Đ` in existing `chunks.text_norm` and rebuilds the derived FTS index from those stored chunks. No original source file or model is needed, including when reimporting the same file returns `unchanged`. Documents, chunks' original text/IDs/offsets, hashes, conversations, settings and run records are preserved.
- Stop all older TreLLM processes before upgrading. After schema 5 is applied, do not use a pre-fix version to write to that database or downgrade its writers: older imports would recreate incompatible normalized text.
- Initial WAL setup retries only transient SQLite busy/locked errors for up to five seconds, restores the normal statement timeout afterward, and closes the connection if initialization fails. Other initialization errors propagate immediately.
- Pending migrations run in one SQLite transaction with the schema version. Failure rolls back the derived data, index and version together and fails startup, allowing a later retry. Up-to-date opens do not acquire a migration writer lock. Large existing indexes may take longer on the first open and need disk space for SQLite's transaction journal; the migration does not load the corpus into Python memory.

## Chat page session and interruption recovery

- The web UI owns one in-memory `ChatSession` per browser page. Requests and messages have stable local identities; selecting another conversation or changing routes does not change their owner. Drafts and partial output survive route changes, but not closing/reloading the browser page. The app requests the browser's normal leave-page warning when there is active or unsaved work.
- History and list reads are versioned. Sending is disabled until the selected history is loaded. A `conv` event confirms the submitted user row; it does not trigger a history fetch while the assistant is still being generated. Only `done` confirms assistant persistence. Errors, missing terminal events and uncertain DELETE responses require an explicit history reload before the next send. If no conversation ID arrived, the user must start a new conversation; no chat POST is retried automatically.
- Reloading history retains unconfirmed messages in a separate local-copy section, distinct from the server context. The composer draft is preserved. Copies can overlap persisted messages after a lost response; the UI does not deduplicate by text or silently treat them as model context. An explicit confirmed discard removes only local drafts/copies. At most 20 conversation views are retained; clean inactive views can be evicted, but active requests and unsaved text cannot.
- Stop sends one `/api/cancel` request and keeps reading the owned stream through HTTP EOF, including after `[DONE]`. Sending remains blocked until both the stream and cancellation response settle. Stop is disabled as soon as a terminal event is received. Navigation/unmount never sends cancellation, and an active conversation cannot be deleted from this UI. Cancellation errors remain with their originating conversation.
- These are client ownership guarantees, not scoped server cancellation. `/api/cancel` is still global and may affect another tab/client. Its response acknowledges a signal, not released generation ownership; an early signal can be cleared by the current runtime client. The UI waits for the actual result and does not claim that a normal completion was cancelled. Network failure cannot establish that the server has stopped; any subsequent busy response is surfaced without automatic retries. No inference/runtime contract is changed here.
- `npm test` covers synthetic DOM, delayed HTTP/SSE responses, navigation, interrupted text, IME, deletion and cancellation ordering. These are protocol checks, not browser screenshots or real-model inference evidence. Rebuild tracked `apps/web/dist` before packaging because wheels ship those static assets.
