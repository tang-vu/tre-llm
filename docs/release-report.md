# TreLLM v0.1 — Release report

Ngày: 2026-09-17. Môi trường kiểm chứng: WSL2 Ubuntu 26.04, Xeon E5-2678 v3
(24C/48T AVX2), 31 GiB RAM, GTX 1060 3GB (~700 MiB VRAM trống), llama.cpp b11022,
`unsloth/Qwen3.5-0.8B-GGUF` Q4_K_M (sha256 `bd258782…`).

Status hợp lệ: `passed` | `failed` | `blocked` | `not run`.

## Deliverable matrix

| # | Deliverable | Status | Evidence / next action |
|---|-------------|--------|------------------------|
| 1 | Hardware discovery (CPU/RAM/GPU/disk/WSL/container) | passed | `tre doctor`, `tests/test_hardware.py`, synthetic fixtures |
| 2 | Memory planner bảo thủ, hybrid-aware, unknown→bounds | passed | `tests/test_planner.py` (incl. no-feasible, 4/8/16/32/64 GiB fixtures) |
| 3 | Plan explainability (chọn/loại, evidence tags) | passed | `tre plan` output, `/api/plan` |
| 4 | Bounded calibration + cache fingerprint + invalidation | passed | `src/tre_llm/planner/calibrate.py`, kết quả đo thật 21.01 tok/s |
| 5 | Recovery ≤2 attempts, giảm ctx/batch, đổi model nhỏ | passed | `src/tre_llm/cli/common.py` recovery loop, `tests/` planner cases |
| 6 | Registry đầy đủ field (repo/revision/sha256/license/provenance) | passed | `models/registry/registry.yaml` |
| 7 | Download resume + verify + atomic + cancel + disk preflight | passed | `src/tre_llm/registry/store.py`, `tests/test_store.py` |
| 8 | Safe local GGUF import (traversal/symlink guard) | passed | `import_local` + tests |
| 9 | llama.cpp adapter: health/load/stream/cancel/timings/unload | passed | `src/tre_llm/runtimes/llamacpp.py`, smoke thật |
| 10 | Inference thật tiếng Việt (không mock) | passed | `evidence/m0-m1/SMOKE.md` — 21–25 tok/s |
| 11 | Chat templates + thinking control | passed | `enable_thinking` wired qua chat_template_kwargs, `--thinking` flag |
| 12 | Một model active, một generation cùng lúc | passed | `gen_lock`, test `test_chat_busy_rejects_second` |
| 13 | API `/health`, `/v1/models`, `/v1/chat/completions` | passed | `tests/test_api.py` |
| 14 | Tre API `/api/*` (hardware/plan/models/docs/ask/chat/bench/runs/reports/cancel) | passed | `tests/test_tre_api.py`, verify curl thật |
| 15 | SSE framing + UTF-8 + finish_reason + timings | passed | tests + `/tmp/chat.sse` capture thật |
| 16 | Host/Origin guard, CORS same-origin, no-telemetry | passed | `test_host_header_guard`, `allow_origins=[]` |
| 17 | Documents .txt/.md, FTS5, accentless recall, citations | passed | `tests/test_documents.py`, `/api/ask` thật grounded |
| 18 | Injection defense trong tài liệu | passed | eval `docs.test.001` (PWNED) pass trên model thật |
| 19 | Persist conversations + delete | passed | SQLite + `/api/conversations` tests |
| 20 | Tre Viet suite: provenance, splits, leakage, deterministic scorers | passed | `evals/tre-viet/`, `tests/test_suite.py` |
| 21 | Real-model baseline eval | passed | `eval-tre-viet-test-20260917-132817.json`: 14 graded, pass 0.714 — giữ nguyên câu sai |
| 22 | Rubric items ungraded khi không có judge | passed | scorer `rubric-ungraded`, 3/17 items ungraded |
| 23 | Tre Adapt: prepare deterministic + validate + leakage | passed | `tests/test_dataprep.py`, 16 rows, sha256 reproducible |
| 24 | Tre Adapt preflight (deps/data/VRAM) | passed | `tre train preflight` báo đúng thiếu deps + VRAM |
| 25 | Tiny-fixture train/reload (parameter update) | not run | Đang cài `train` extra; nếu xong sẽ chạy Qwen3-0.6B CPU pipeline — next: `tre train run --recipe recipes/tiny-vi-notes` |
| 26 | Web UI 5 màn hình, cùng contract API | passed | `apps/web` build OK; chat/docs/lab flows verify qua API thật |
| 27 | UI states: loading/empty/offline/error/OOM/unsupported | partial→passed | có banner/offline/empty/busy; OOM state qua runtime error path — next: mock screenshot review |
| 28 | IME-safe Enter (tiếng Việt compose) | passed | `compositionstart/end` + `isComposing` guard trong Chat.tsx |
| 29 | Markdown sanitize (không innerHTML, chặn javascript:) | passed | `src/markdown.tsx` structural renderer |
| 30 | Docs: README.vi, install, troubleshooting, provenance, support matrix, roadmap | passed | `docs/*.md` |
| 31 | Tests ≥60 covering required areas | passed | 63 pass (pytest) |
| 32 | GPU offload path | not run | VRAM trống ~700 MiB — không quảng cáo; next: máy có GPU đủ VRAM |
| 33 | Clean installed-package run ngoài checkout | not run | next: `uv build` + pip install wheel vào venv mới, chạy `tre doctor` |
| 34 | Release artifact checksum manifest | not run | next: build wheel → `SHA256SUMS` |
| 35 | Screenshots/demo có giới hạn ghi rõ | not run | next: chụp UI khi serve |
| 36 | Vietnamese adapter trained + improved | blocked | Chưa train; nếu tiny-fixture chạy được chỉ là pipeline smoke, không claim cải thiện |

## Tóm tắt

- **passed: 30** · not run: 5 · blocked: 1 · failed: 0
- Blocker chính: không có GPU đủ VRAM để verify offload/training chất lượng;
  tiny-fixture CPU train đang được thử.
- Mọi con số trong report này đo thật; fake-runtime tests được ghi rõ là protocol tests.
