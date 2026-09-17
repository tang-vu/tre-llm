# Provenance & License

## Mã nguồn TreLLM

- License: Apache-2.0. Tác giả: Tăng Minh Vũ / tang-vu.
- Không nhúng trọng số model vào repo. Model tải về máy người dùng khi `tre models pull`.

## Model trong registry

Mỗi entry trong `models/registry/registry.yaml` ghi: upstream repo, revision, file
list, size, sha256, license, license_url, source_url. Kiểm chứng:

| Model | Upstream | License | sha256 kiểm chứng |
|-------|----------|---------|-------------------|
| Qwen3.5-0.8B Q4_K_M | `unsloth/Qwen3.5-0.8B-GGUF` (base: `Qwen/Qwen3.5-0.8B`) | Apache-2.0 (Qwen) | `bd258782…dc517` — khớp HF `lfs.oid` |

Quan trọng: `x-linked-etag` trên HF resolve **không** phải sha256 file — registry
luôn dùng `lfs.oid` từ tree API. Model upstream giữ nguyên danh tính; TreLLM không
claim tự huấn luyện.

## Runtime

| Thành phần | Nguồn | Integrity |
|-----------|-------|-----------|
| llama.cpp b11022 ubuntu-x64 | GitHub `ggml-org/llama.cpp` releases | tar sha256 `9be8b82e…daed` |

## Dữ liệu eval & training

- `evals/tre-viet/`: curated/synthetic, viết tay cho dự án, CC-BY-4.0 — chi tiết `evals/tre-viet/SUITE.md`.
- `recipes/tiny-vi-notes/`: fixture viết tay, CC-BY-4.0 — không dùng cho quality training.
- Không dùng dữ liệu crawl chưa rõ license trong v0.1.

## Dependencies

Xem `pyproject.toml`. Chính: FastAPI, uvicorn, pydantic, httpx, typer, rich, pyyaml,
platformdirs, psutil. Extra `train`: torch, transformers, peft, trl, datasets, accelerate.
Web UI: React 18 + Vite (dev-only build; runtime không cần node).
