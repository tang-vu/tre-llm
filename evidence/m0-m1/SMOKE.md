# M0-M1 smoke evidence — 2026-09-17, WSL2 Xeon E5-2678 v3, 31 GiB RAM

## Runtime
- llama.cpp b11022 ubuntu-x64, `llama-server --version` → `0.4.1-dev (build 11022, commit f172be756)`
- tar sha256: 9be8b82ef44c5488155ce718d1ab4dcbd6b3aa999c70d1d44dc0ac11e868daed

## Model
- unsloth/Qwen3.5-0.8B-GGUF — Qwen3.5-0.8B-Q4_K_M.gguf, 532,517,120 B
- sha256 bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517 (khớp HF tree API lfs.oid)
- NOTE: x-linked-etag trên resolve HEAD = de9bcb3f… ≠ sha256 file → registry dùng tree API.

## Real inference (đo thật, không mock)
- `tre chat --once "Hà Nội có bao nhiêu quận nội thành?"` → 22.6 tok/s decode, 135 tok/s prompt
- `POST /v1/chat/completions` qua `tre serve` → 22.9 tok/s, finish_reason=stop
- enable_thinking=false cần thiết: mặc định Qwen3.5 sinh reasoning_content trước
- Model 0.8B hallucination vẫn xảy ra (câu trả lời quận nội thành sai) — đây là giới hạn chất lượng thật, không che giấu.

## Commands verified
- `tre doctor` — hardware probe đầy đủ (CPU/RAM/GPU/disk, WSL2 detect)
- `tre models list` — registry + installed index
- `tre chat --once` — managed subprocess + streaming + clean shutdown
- `tre serve` — /health, /v1/models, /v1/chat/completions OK
