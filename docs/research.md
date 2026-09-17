# Research log — 2026-09-17

Nguồn chính đã truy cập thật từ môi trường dev (WSL2).

## Runtime

- llama.cpp GitHub releases: `https://api.github.com/repos/ggml-org/llama.cpp/releases` — release mới nhất dạng `b11022` (2026-09). Tag `v0.4.1` chỉ chứa nightly-tag pointer.
- Asset dùng: `llama-b11022-bin-ubuntu-x64.tar.gz` (16.1 MB), sha256 tar `9be8b82e…8daed`. Đã chạy: `llama-server --version` → `0.4.1-dev (build 11022, f172be756)`; `--list-devices` → "(none)" trên CPU build.
- Flags verify từ `--help` b11022: `--model --host --port --parallel --ctx-size --threads --batch-size --ubatch-size --jinja (default on) --api-key --alias --no-webui/--no-ui --metrics --timeout --chat-template-kwargs --flash-attn --cache-type-k/v --n-gpu-layers`.
- Note: flags tiến hóa nhanh (`--no-webui` deprecated → `--no-ui` còn hoạt động). Cần versioned adapter.

## Model candidates (HF API truy cập thật)

| Repo | Trạng thái | Ghi chú |
|------|-----------|---------|
| `unsloth/Qwen3.5-0.8B-GGUF` | OK, Apache-2.0 | Đủ quant. **Đã tải + chạy thật Q4_K_M 532MB** — sha256 `bd2587…`, 25 tok/s CPU |
| `Qwen/Qwen3.5-0.8B` | OK, Apache-2.0 | Safetensors nguồn; có chat_template.jinja |
| `Qwen/Qwen3-0.6B-GGUF` | OK, Apache-2.0 | Chỉ Q8_0 (651MB) |
| `ggml-org/Qwen3-0.6B-GGUF` | OK | Q4_0/Q8_0/f16/BF16 (428MB Q4_0) |
| `Qwen/Qwen3-1.7B-GGUF` | OK, Apache-2.0 | Chỉ Q8_0 (1.83GB) |
| `Qwen/Qwen3-4B-GGUF` | OK, Apache-2.0 | Q4_K_M 2.33GiB + quants khác |
| `Qwen/Qwen3-8B-GGUF` | OK, Apache-2.0 | Q4_K_M 4.68GiB |
| `unsloth/Qwen3-4B-Instruct-2507-GGUF` | OK, Apache-2.0 | Đủ quant |
| `Qwen/Qwen2.5-1.5B/3B-Instruct-GGUF` | OK | 3B license "other" (research-only?) — cần xem LICENSE trước khi dùng |
| `Qwen/Qwen3.5-0.8B-GGUF`, `bartowski/*` | HTTP 401 | Repo không public/gated — không dùng |

### Phát hiện quan trọng

1. `x-linked-etag` ≠ sha256 file (đo thật: etag `de9bcb…` vs lfs.oid `bd2587…` trùng sha256 file tải về). Integrity phải lấy từ `GET /api/models/{repo}/tree/{rev}` → `lfs.oid`.
2. Qwen3.5-0.8B thinking mặc định ON → 150 token đầu toàn `reasoning_content`. Cần `chat_template_kwargs.enable_thinking=false` hoặc ngân sách token lớn. Đã verify cả hai đường.
3. llama-server trả `timings` (prompt_per_second, predicted_per_second) + `usage` chuẩn — dùng cho bench.
4. CORS warning: server mặc định allow `*` khi không có API key → Tre tự quản Host/Origin ở tầng FastAPI và bind loopback.

## Unknowns còn lại

- Chất lượng tiếng Việt thực tế giữa 0.8B vs 4B vs 8B → đo bằng Tre Viet Lab (M4), không suy đoán.
- GGUF export cho Qwen3.5 adapter (M4) — kiểm tra `convert_hf_to_gguf` hỗ trợ arch.
- Vulkan path trên GTX 1060 trong WSL2 — NVIDIA Vulkan không khả dụng trong WSL → GPU path ghi "not run".

## Registry v0.1 (chọn)

- Tiny → `unsloth/Qwen3.5-0.8B-GGUF` Q4_K_M — TESTED trên máy dev
- Lite → `Qwen/Qwen3-1.7B-GGUF` Q8_0 — documented
- Core → `Qwen/Qwen3-4B-GGUF` Q4_K_M — dự kiến test (calibration)
- Pro → `Qwen/Qwen3-8B-GGUF` Q4_K_M — documented/tested nếu budget cho phép
