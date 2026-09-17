# STATUS — TreLLM v0.1

Cập nhật lần cuối: 2026-09-17 (session 3, sau hướng "model riêng")

## Trạng thái milestone

| MS | Nội dung | Trạng thái |
|----|----------|-----------|
| M0 | Khảo sát + quyết định | DONE — evidence/m0-m1/SMOKE.md |
| M1 | Vertical slice (doctor→pull→chat) | DONE — `tre doctor/models/chat/serve` chạy inference thật |
| M2 | Tre Fit (planner/calibrate/recovery) | DONE — calibration đo thật 21.01 tok/s, RSS 904 MiB |
| M3 | Product workflows (UI/API/documents) | DONE — web UI 5 màn hình build OK, `/api/chat` SSE persist verify thật, docs Q&A grounded có trích dẫn |
| M4 | Tre Viet Lab + Tre Adapt | DONE — suite 22 items, eval test split thật 2 lần; dataprep/validate/preflight OK; train CPU smoke XONG (adapter LoRA + report) |
| M5 | Release prep | DONE — wheel+sdist build OK, clean install verify OK, SHA256SUMS, LICENSE/docs/CI/templates |

## Phần cứng dev (đo thật 2026-09-17)

- Host: Windows 11 + WSL2 Ubuntu 26.04 (`/mnt/d/Github/tre-llm`)
- CPU: Intel Xeon E5-2678 v3, 24 cores / 48 threads, AVX2 (không AVX-512)
- RAM: 31 GiB total, ~29 GiB available
- GPU: NVIDIA GTX 1060 3GB, driver 560.94 / CUDA 12.6 — **chỉ ~440 MiB VRAM trống** → CPU inference là đường chính
- Disk: WSL `/` còn ~756 GB; `D:` còn ~38 GB
- Python 3.12.14 (uv 0.12.15 user-local); Node v22.14.0, npm 10.9.2

## Quyết định kỹ thuật (M0)

- Runtime chính: **llama.cpp b11022** ubuntu-x64 CPU binary, sha256 tar `9be8b82e…`
- Model test thật: **`unsloth/Qwen3.5-0.8B-GGUF` `Qwen3.5-0.8B-Q4_K_M.gguf`** (532,517,120 B)
  - sha256 = `bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517` (khớp HF tree API `lfs.oid`; `x-linked-etag` KHÔNG khớp → registry dùng `lfs.oid`)
- `enable_thinking=false` bắt buộc cho chat thường (Qwen3.5 default thinking)
- Registry 4 profile: Tiny=Qwen3.5-0.8B-Q4_K_M, Lite=Qwen3-1.7B-Q8_0, Core=Qwen3-4B-Q4_K_M, Pro=Qwen3-8B-Q4_K_M

## Tre Viet Lab — kết quả thật (Qwen3.5-0.8B, llama.cpp CPU)

- Suite: `evals/tre-viet/` — 22 items (5 dev / 17 test), 4 category (qna/extract/notes/docs), provenance+license mỗi item
- Baseline dev (13:26): 4 graded, mean 0.625, pass 0.5 — `eval-tre-viet-dev-20260917-132620.json`
- Test run 1 (13:28): 14 graded, mean 0.75, pass 0.714 — `eval-tre-viet-test-20260917-132817.json`
- Test run 2 (14:10): 14 graded, mean 0.679, pass 0.643 — `eval-tre-viet-test-20260917-141038.json`
- Variance giữa 2 test run là thật (sampling). docs 5/5 pass; qna/extract có câu sai giữ nguyên; notes 3 câu rubric ungraded (cần judge)
- Scorer `forbid` mới: câu bị cấm (PWNED injection, refusal) ép fail trên mọi grader
- Reports trong `/root/.local/share/tre-llm/eval-results/`

## Tre Adapt — trạng thái

- `tre train prepare` → 16 dòng → 13 train/3 eval, sha256 `4b7bcd10…` (deterministic, seed 42)
- `tre train validate` → OK (schema + tiếng Việt + leakage vs eval suite)
- `tre train preflight` → OK sau khi cài `pip install tre-llm[train]` (torch 2.8.0, trl 0.21.0)
- Recipe `tiny-vi-notes`: `device: cpu`, `cpu_smoke_ok: true` — pipeline test, KHÔNG phải cải thiện chất lượng
- `tre train run` XONG: 45.6 phút CPU, dừng ở step 2/4 (budget 30ph enforce ở step granularity → overshoot), train_loss 3.705, adapter LoRA r=8 (112 tensors) verify load được bằng peft — `training-out/tiny-vi-notes/` + `run-report.json` (status `pipeline-smoke`, `time_budget_exceeded: true`)
- Fix transformers 4.57: `max_time` bị xoá khỏi TrainingArguments → bound bằng `_time_budget_callback`
- **Session 3 — loop "model riêng" đã đóng:**
  - `tre train export --adapter … --out x.gguf` — merge LoRA vào base → convert_hf_to_gguf.py (llama.cpp source cache `~/.cache/tre-llm/llama.cpp-b11022-src`) → llama-quantize Q4_K_M → GGUF + metadata sidecar
  - `tre models import` nhận `--base-model/--adapter/--license/--notes` → provenance lưu trong installed.json, hiện trong `tre models list`
  - Dataprep hỗ trợ HF datasets (`hf:` source) + format sharegpt/conversations, prompt_response, instruction+output, text; `max_chars` filter
  - `run.py` train trên `messages` (chat template thật của base model qua TRL), fallback `text`
  - Recipe thật `recipes/tre-vi-0.6b/`: 3 nguồn (5CD-AI/Vietnamese-Multi-turn-Chat-Alpaca Apache-2.0, vlinhd11/vietnamese-sft-10k CC-BY-4.0, fixture local) → **3,742 dòng sạch** (3,554 train/188 eval, 1 dup, 1 invalid, 2,272 long dropped), sha256 `5b065ae1…`
  - Notebook Kaggle free-tier: `notebooks/train-tre-vi-kaggle.ipynb` (T4/P100, clone repo → prepare → train → zip adapter). `max_minutes: 180`
  - Preflight `tre-vi-0.6b` trên máy này: **exit 2, [THIẾU] VRAM 882 MiB < 8 GiB** — đúng thiết kế, không chạy được local

## Verified end-to-end (2026-09-17)

- **66 unit/protocol tests pass**, `ruff check` sạch
- `tre serve --port 8471` → `/api/status` upstream_ready=true, model `qwen3.5-0.8b-q4_k_m`
- `POST /api/chat` SSE: conv→60 tokens→done(21.9 tok/s decode, 124.5 tok/s prompt)→[DONE]; persist SQLite
- `POST /api/ask` câu không dấu → FTS5 → trả lời grounded kèm trích dẫn [1], `grounded:true`
- Web UI React build OK (vite, dist ~190 KB) — track trong git để wheel ship sẵn
- `uv build` → wheel + sdist OK (wheel build từ sdist → sdist đủ file)
- Clean install: venv mới + wheel → `tre --version` = 0.1.0, `tre doctor` thấy runtime+model
- `tre report --format md` → markdown sạch, không lộ path cá nhân
- **`tre-vi-0.6b-q4_k_m` GGUF chạy thật** qua llama.cpp (~37 tok/s, "Hà Nội có 12 quận." — style ngắn gọn từ adapter)
- **Eval dev trước/sau (n=5, mẫu nhỏ):** base Qwen3-0.6B mean 0.375/pass 0.25 → tre-vi-0.6b mean 0.625/pass 0.5 — `eval-tre-viet-dev-20260917-160057.json` / `-160125.json`
- Exit codes verify: `train validate`/`preflight` fail → exit 2 (lưu ý: `$?` trong exec wrapper luôn đọc 0 — phải chạy lệnh đơn để xem code thật)

## Lệnh chạy đã kiểm chứng

```bash
.venv/bin/tre serve --port 8471
.venv/bin/python -m pytest tests/ -q          # 63 pass
.venv/bin/ruff check .                         # clean
cd apps/web && npm install && npm run build
.venv/bin/tre eval --suite tre-viet --split test
.venv/bin/tre train prepare --recipe recipes/tiny-vi-notes/recipe.yaml
.venv/bin/tre train validate --data recipes/tiny-vi-notes/prepared.jsonl
.venv/bin/tre train preflight --recipe recipes/tiny-vi-notes/recipe.yaml
.venv/bin/tre train run --recipe recipes/tiny-vi-notes/recipe.yaml
.venv/bin/tre train export --adapter training-out/tiny-vi-notes/adapter --out /tmp/x.gguf
.venv/bin/tre models import x.gguf --id my-model --base-model Qwen/Qwen3-0.6B --license apache-2.0
.venv/bin/tre eval --suite tre-viet --split dev --model tre-vi-0.6b-q4_k_m
.venv/bin/tre report --format md --out /tmp/tre-report
~/.local/bin/uv build
```

## Blocker / rủi ro

- GTX 1060 3GB: VRAM trống ~440 MiB → GPU path "not run", không quảng cáo.
- Process nền qua exec `&` bị kill khi shell đóng → spawn train/eval phải qua exec timeout=0.
- `/api/models/select` cần restart server để đổi model active.
- PDF/OCR chưa hỗ trợ (v0.1 chỉ .txt/.md/.markdown).
- Rubric items cần judge model hoặc chấm tay.
- Suite nhỏ (22 items) — phát hiện regression thô, không phải thang đo chất lượng tuyệt đối.

## Việc tiếp theo

1. Chạy `notebooks/train-tre-vi-kaggle.ipynb` trên Kaggle (P100/T4 miễn phí) → tải adapter về → `tre train export` → `tre models import` → eval trước/sau → đó mới là `tre-vi` run nghiêm túc
2. Push repo nếu user yêu cầu (chưa push)
3. Roadmap: GPU pilot khi có máy đủ VRAM; judge model cho rubric items; PDF/OCR ingest
