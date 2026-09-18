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
