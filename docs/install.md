# Cài đặt TreLLM

## Yêu cầu hệ thống

| Thành phần | Tối thiểu | Khuyên dùng |
|-----------|-----------|-------------|
| Python | 3.11 | 3.12 |
| RAM | 4 GiB trống | 8+ GiB trống |
| Disk | 3 GiB | 10 GiB |
| OS | Linux x86_64 AVX2, macOS arm64, WSL2 | — |
| GPU | không bắt buộc | CUDA ≥ 4 GiB VRAM để offload |

CPU cần AVX2 (llama.cpp prebuilt yêu cầu). Máy ARM Linux/macOS dùng được nhưng
v0.1 mới kiểm chứng x86_64 Linux — xem `docs/support-matrix.md`.

## Cài từ source (khuyên dùng lúc này)

```bash
git clone https://github.com/tang-vu/tre-llm.git && cd tre-llm
uv sync                                  # tạo .venv, lock deps
cd apps/web && npm install && npm run build && cd ../..   # build UI (tuỳ chọn nhưng nên)
.venv/bin/tre doctor
.venv/bin/tre setup
.venv/bin/tre serve
```

Không build UI thì `tre serve` vẫn chạy API, trang `/` hiện thông báo thay UI.

## Cài từ wheel

```bash
uv build                                 # wheel gồm UI đã build + registry + evals
pip install dist/tre_llm-*.whl
tre setup && tre serve
```

## Extra: Tre Adapt (training)

```bash
uv sync --extra train    # torch + transformers + peft + trl + datasets (~3 GiB)
```

Chỉ cần cho `tre train run`. `prepare`/`validate`/`preflight` không cần extra này.

## Biến môi trường

| Biến | Ý nghĩa |
|------|---------|
| `TRE_LLM_HOME` | Đổi thư mục dữ liệu (mặc định platformdirs user-data) |
| `TRE_LLM_DOWNLOAD_MAX_GB` | Ngân sách tải model (mặc định 8) |

## Gỡ cài / reset

Xoá thư mục dữ liệu in ra bởi `tre doctor --json` (trường `paths`), và `.venv`.
Model `.part` chưa hoàn tất nằm trong `cache/downloads/` — xoá thủ công nếu muốn.
