# Troubleshooting

## `tre setup` thất bại khi tải model

- Kiểm tra mạng + quyền ghi disk: `tre doctor` hiện disk trống từng mount.
- Download bị ngắt giữa chừng: file `.part` được giữ — chạy lại `tre models pull <id>` sẽ resume.
- Lỗi checksum: file bị hỏng → xoá file trong `cache/models/<id>/` rồi pull lại.
- Hết disk: planner báo trước; giải phóng disk hoặc chọn profile nhỏ hơn (`--goal light`).

## `tre serve` mở nhưng chat báo "Runtime chưa sẵn sàng"

- Model chưa cài: `tre models list` → `tre models pull <id>` hoặc `tre setup`.
- Port bận: `tre serve --port <khác>`.
- llama-server chết ngầm: `tre doctor` kiểm tra lại; log lỗi in khi `tre serve` khởi động.

## Trả lời dài dòng / toàn "suy luận" không ra câu trả lời

Qwen3.5 mặc định thinking. TreLLM truyền `enable_thinking=false` cho chat thường.
Muốn thinking: `tre chat --thinking`. Nếu bị cắt giữa chừng → tăng `--max-tokens`.

## Chậm trên CPU

- Model 0.8B đo ~21 tok/s trên Xeon E5 24 nhân. CPU yếu hơn sẽ chậm hơn tương ứng.
- `tre plan --goal light` chọn cấu hình nhẹ hơn.
- Chỉ 1 generation cùng lúc (cố ý — máy yếu không nên xếp hàng song song).

## Hết RAM / bị kill khi load model

- Đóng app khác, `tre plan` lại để xem ước lượng thật.
- Recovery tự động: giảm context/batch, đổi model nhỏ hơn đã cài — log in ra khi `tre serve` start.

## Web UI trắng / 404 assets

- Chưa build: `cd apps/web && npm install && npm run build`.
- Chỉ có API: trang `/` báo "UI chưa được build" — API vẫn hoạt động tại `/api/*`, `/v1/*`.

## `tre train` báo thiếu torch

`uv sync --extra train` (kéo ~3 GiB). CPU training chỉ dùng cho pipeline test —
quality cần GPU ≥ 4 GiB VRAM trống.

## GPU không được dùng

v0.1: llama.cpp build là CPU-only. GPU path chưa verify (GTX 1060 không đủ VRAM trống).
Xem `docs/support-matrix.md`.
