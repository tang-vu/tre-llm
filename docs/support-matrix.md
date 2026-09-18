# Support matrix — TreLLM v0.1

Chỉ những ô "verified" có evidence đo thật trên máy dev. Các ô khác là dự kiến
từ thiết kế — chưa kiểm chứng thì ghi rõ.

## Nền tảng

| Nền tảng | Trạng thái | Ghi chú |
|----------|-----------|---------|
| Linux x86_64 + WSL2 (Ubuntu 26.04) | **verified** | Môi trường dev; mọi evidence đo ở đây |
| Linux x86_64 native | expected | Cùng binary llama.cpp ubuntu-x64; chưa test trên máy thật |
| Windows native | not run | Phát triển qua WSL2; `tre` chưa test trên PowerShell |
| macOS arm64 | not run | Cần llama.cpp darwin-arm64 build — đường dẫn đã thiết kế, chưa có máy test |
| Container (Docker) | expected | `in_container` được phát hiện; chưa có image chính thức |

## Phần cứng

| Cấu hình | Trạng thái | Evidence |
|----------|-----------|----------|
| CPU-only, 31 GiB RAM, AVX2 | **verified** | `evidence/m0-m1/SMOKE.md`, bench 21 tok/s |
| CPU-only, 4 GiB RAM | experimental | Planner hỗ trợ nhưng chưa có máy thật → không khẳng định chạy được |
| NVIDIA GPU ≥ 4 GiB trống | not run | GTX 1060 3GB chỉ còn ~700 MiB trống → không test được offload |
| Unified memory (Apple Silicon) | not run | Planner có nhánh `unified_memory`, chưa verify |

## Model trong registry

| Profile | Upstream | Quant | Verified? |
|---------|----------|-------|-----------|
| Tiny | `unsloth/Qwen3.5-0.8B-GGUF` | Q4_K_M | **yes** — sha256 khớp, inference + eval + bench đo thật |
| Lite | Qwen3-1.7B (unsloth) | Q8_0 | metadata — chưa tải, chưa chạy |
| Core | Qwen3-4B (unsloth) | Q4_K_M | metadata — chưa tải |
| Pro | Qwen3-8B (unsloth) | Q4_K_M | metadata — chưa tải |

## Tính năng

| Tính năng | Trạng thái |
|-----------|-----------|
| Chat streaming SSE, persist SQLite | verified |
| Hỏi đáp tài liệu .txt/.md/.pdf + trích dẫn | verified (cả query không dấu; PDF = text layer) |
| Eval suite dev/test + report | verified trên Qwen3.5-0.8B |
| `tre train prepare/validate/preflight` | verified |
| `tre train run` (LoRA) | pipeline-test only — cần `train` extra; chưa chạy run thật |
| GPU offload | not run — không quảng cáo |
| PDF scan (không text layer) / OCR | blocked — báo rõ trong API/UI |
