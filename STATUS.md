# STATUS — TreLLM v0.1

Cập nhật lần cuối: 2026-09-17 (session 2)

## Trạng thái milestone

| MS | Nội dung | Trạng thái |
|----|----------|-----------|
| M0 | Khảo sát + quyết định | DONE — evidence/m0-m1/SMOKE.md |
| M1 | Vertical slice (doctor→pull→chat) | DONE — `tre doctor/models/chat/serve` chạy inference thật |
| M2 | Tre Fit (planner/calibrate/recovery) | DONE core — calibration đo thật 21.01 tok/s, RSS 904 MiB |
| M3 | Product workflows (UI/API/documents) | DONE core — web UI 5 màn hình build OK, `/api/chat` SSE persist verify thật, docs Q&A grounded có trích dẫn |
| M4 | Tre Viet Lab + Tre Adapt | IN PROGRESS — runner/scorer/bench skeleton, cần dataset + train pilot |
| M5 | Release prep | pending |

## Phần cứng dev (đo thật 2026-09-17)

- Host: Windows 11 + WSL2 Ubuntu 26.04 (`/mnt/d/Github/tre-llm`)
- CPU: Intel Xeon E5-2678 v3, 24 cores / 48 threads, AVX2 (không AVX-512)
- RAM: 31 GiB total, ~29 GiB available
- GPU: NVIDIA GTX 1060 3GB, driver 560.94 / CUDA 12.6 — **chỉ ~763 MiB VRAM trống** → CPU inference là đường chính
- Disk: WSL `/` còn 767 GB; `D:` còn 49 GB
- Python system 3.14 (không pip); uv 0.12.15 + CPython 3.12.14 user-local
- Node v22.14.0, npm 10.9.2, g++ 15.2.0

## Quyết định kỹ thuật (M0)

- Runtime chính: **llama.cpp b11022** ubuntu-x64 CPU binary, sha256 tar `9be8b82e…`
- Model test thật: **`unsloth/Qwen3.5-0.8B-GGUF` `Qwen3.5-0.8B-Q4_K_M.gguf`** (532,517,120 B)
  - sha256 thật = `bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517` (khớp HF tree API `lfs.oid`; `x-linked-etag` KHÔNG khớp → registry dùng `lfs.oid`)
- `enable_thinking=false` bắt buộc cho chat thường (Qwen3.5 default thinking → dài, chạm max_tokens)
- Registry 4 profile: Tiny=Qwen3.5-0.8B-Q4_K_M, Lite=Qwen3-1.7B-Q8_0, Core=Qwen3-4B-Q4_K_M, Pro=Qwen3-8B-Q4_K_M

## Verified end-to-end hôm nay (2026-09-17)

- 50 unit/protocol tests pass (fake runtime, không phải evidence inference)
- `tre serve --port 8471` → UI tại `/`, `/api/status` trả upstream_ready=true, model active `qwen3.5-0.8b-q4_k_m`
- `POST /api/chat` SSE: conv→60 tokens→done(`finish_reason=length`, 21.9 tok/s decode, 124.5 tok/s prompt)→[DONE]; user+assistant persist vào SQLite
- `POST /api/documents` (ha-noi.md) → `POST /api/ask` câu hỏi **không dấu** "Ha Noi co bao nhieu quan?" → FTS5 match → model trả lời grounded kèm trích dẫn [1], `grounded:true`
- Web UI React build OK (vite 5.4, 38 modules, dist ~190 KB)

## Lệnh chạy đã kiểm chứng

```bash
.venv/bin/tre serve --port 8471        # API + UI, model tự load
.venv/bin/python -m pytest tests/ -q   # 50 pass
cd apps/web && npm install && npm run build
```

## Blocker / rủi ro

- GTX 1060 3GB: VRAM trống quá ít → GPU path "not run", không quảng cáo.
- Process chạy nền qua exec `&` bị kill khi shell đóng → `llama-server` orphan 2 lần, đã dọn; runtime manager cần test kill-on-exit.
- `tre serve` hiện chỉ load model lúc start — `/api/models/select` yêu cầu restart (đã ghi trong note API).

## Việc tiếp theo

1. M4: evals/tre-viet dataset thật + runner + báo cáo + baseline thật trên Qwen3.5-0.8B
2. M4: Tre Adapt — data prep/validation/preflight; tiny-fixture train nếu khả thi, không thì ghi blocked
3. M5: README.vi, release-report.md, docs release, clean-install verify, checksum manifest
4. Dọn `node_modules`/dist khỏi git nếu chưa ignore
