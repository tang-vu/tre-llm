# STATUS — TreLLM v0.1

Cập nhật lần cuối: 2026-09-17 (session 1)

## Trạng thái milestone

| MS | Nội dung | Trạng thái |
|----|----------|-----------|
| M0 | Khảo sát + quyết định | DONE — evidence/m0-m1/SMOKE.md |
| M1 | Vertical slice (doctor→pull→chat) | DONE — `tre doctor/models/chat/serve` chạy inference thật |
| M2 | Tre Fit (planner/calibrate/recovery) | IN PROGRESS — memory+select+calibrate đã viết, cần test |
| M3 | Product workflows (UI/API/documents) | partial — API + documents service OK, thiếu UI thật |
| M4 | Tre Viet Lab + Tre Adapt | partial — runner/scorer/bench/train skeleton |
| M5 | Release prep | pending |

## Phần cứng dev (đo thật 2026-09-17)

- Host: Windows 11 + WSL2 Ubuntu 26.04 (`/mnt/d/Github/tre-llm`)
- CPU: Intel Xeon E5-2678 v3, 24 cores / 48 threads, AVX2 (không AVX-512)
- RAM: 31 GiB total, ~29 GiB available
- GPU: NVIDIA GTX 1060 3GB, driver 560.94 / CUDA 12.6 — **chỉ ~763 MiB VRAM trống** (Windows chiếm ~2.2 GiB) → quyết định CPU inference là đường chính
- Disk: WSL `/` còn 767 GB; `D:` còn 49 GB
- Python system 3.14 (không pip); đã cài uv 0.12.15 + CPython 3.12.14 user-local
- Node v22.14.0, npm 10.9.2, g++ 15.2.0

## Quyết định kỹ thuật (M0)

- Runtime chính: **llama.cpp b11022** ubuntu-x64 CPU binary (16.1 MB), sha256 tar `9be8b82ef44c5488155ce718d1ab4dcbd6b3aa999c70d1d44dc0ac11e868daed`
  - `llama-server --version` → `0.4.1-dev (build 11022, commit f172be756)`
- Model test thật: **`unsloth/Qwen3.5-0.8B-GGUF` `Qwen3.5-0.8B-Q4_K_M.gguf`** (532,517,120 B)
  - sha256 thật = `bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517` (khớp HF tree API `lfs.oid`)
  - **Bài học**: `x-linked-etag` trên HEAD resolve KHÔNG khớp sha256 file → registry phải dùng tree API `lfs.oid`
- Bằng chứng inference thật: `evidence/m0-smoke/` — 25.0 tok/s decode, 111 tok/s prefill, tiếng Việt OK khi `enable_thinking=false` (Qwen3.5 mặc định thinking → cần chat_template_kwargs)
- Registry 4 profile: Tiny=Qwen3.5-0.8B-Q4_K_M, Lite=Qwen3-1.7B-Q8_0, Core=Qwen3-4B-Q4_K_M, Pro=Qwen3-8B-Q4_K_M (chi tiết `models/registry/registry.yaml`)
- Download budget: 8 GiB; đã dùng 0.50 GiB (0.8B). Dự kiến thêm 4B (2.33 GiB) cho calibration.

## Lệnh chạy đã kiểm chứng

```bash
# llama-server thủ công (đã chạy OK):
~/.cache/tre-llm/runtimes/llama.cpp-b11022/llama-b11022/llama-server \
  --model ~/.cache/tre-llm/models/qwen3.5-0.8b-q4_k_m/Qwen3.5-0.8B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8391 --ctx-size 4096 --parallel 1 --threads 8 --no-webui
# chat_template_kwargs {"enable_thinking": false} để tắt thinking
```

## Blocker / rủi ro

- GTX 1060 3GB: VRAM trống quá ít → không test GPU offload có ý nghĩa. Ghi "not run" cho GPU path.
- Đường dẫn file tool vs WSL: file tools ghi qua Windows side (`D:\`), shell chạy WSL (`/mnt/d`). Cùng một file nhưng cần nhớ khi dùng /tmp.
- Qwen3.5 thinking mode: default ON; Tre phải truyền `chat_template_kwargs.enable_thinking` rõ ràng.

## Việc tiếp theo

1. Viết docs M0 (product-spec, architecture, research, ADR-001 runtime/model)
2. Scaffold package + venv + lockfile
3. M1: doctor, registry pull/import, llama.cpp adapter, `tre chat` streaming, `tre serve`
