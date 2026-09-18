# TreLLM — Hướng dẫn tiếng Việt

**LLM tiếng Việt, vừa sức máy bạn.**

TreLLM giúp bạn chạy mô hình ngôn ngữ trên chính máy mình, bằng tiếng Việt,
với cấu hình được chọn tự động theo phần cứng — và bằng chứng đo lường trung thực.

## 1. Cài đặt

Yêu cầu: Python 3.11 hoặc 3.12, ~4 GiB RAM trống, ~3 GiB disk trống, Linux/macOS/WSL2.

```bash
git clone https://github.com/tang-vu/tre-llm.git
cd tre-llm
uv sync                    # tạo .venv + cài deps (khuyên dùng)
# hoặc: python -m venv .venv && .venv/bin/pip install -e .
```

Mọi lệnh dưới đây chạy qua `.venv/bin/tre` (hoặc `tre` nếu đã activate venv).

## 2. Thiết lập lần đầu

```bash
tre doctor      # quét phần cứng — chỉ đọc, không đổi gì
tre plan        # xem kế hoạch đề xuất + giải thích + phương án bị loại
tre setup       # tải llama.cpp + model phù hợp (hỏi trước khi tải)
tre chat        # thử chat ngay trong terminal
tre serve       # mở web UI tại http://127.0.0.1:8471
```

`tre setup` tôn trọng mục tiêu `--goal`: `light` (nhẹ máy), `balanced` (mặc định),
`quality` (ưu tiên chất lượng, cần nhiều RAM hơn).

## 3. Dùng hằng ngày

### Trò chuyện
- Web UI: `tre serve` → mở http://127.0.0.1:8471 → tab **Trò chuyện**.
- Terminal: `tre chat` (interactive) hoặc `tre chat --once "câu hỏi"`.
- Hội thoại lưu cục bộ trong SQLite — không gửi đi đâu.

### Hỏi tài liệu
- Tab **Tài liệu**: kéo thả file `.txt`/`.md` → hỏi đáp kèm trích dẫn `[1]`.
- Tìm kiếm **không cần gõ dấu**: "ha noi" vẫn khớp "Hà Nội".
- Giới hạn: file ≤ 4 MiB, text ≤ 400K ký tự. PDF scan chưa hỗ trợ (cần OCR).

### Đo hiệu năng thật
```bash
tre bench --quick       # 1 mẫu nhanh
tre bench               # đo đầy đủ: load, TTFT, decode tok/s, RSS đỉnh
tre report --format md  # xuất báo cáo từ các lần đo
```

### Đánh giá tiếng Việt (Tre Viet Lab)
```bash
tre eval --suite tre-viet --split dev      # 5 câu, iterate nhanh
tre eval --suite tre-viet --split test     # 17 câu held-out, chậm trên CPU
# rubric items: thêm --judge <model-id> để model khác chấm (đổi grader thành judge:<id>)
tre eval --split dev --model tre-vi-0.6b-q4_k_m --judge qwen3.5-0.8b-q4_k_m
tre report --format html                   # tổng hợp mọi kết quả đo
```

### Huấn luyện thích ứng (Tre Adapt)
```bash
uv sync --extra train      # cài torch/transformers/peft/trl (nặng ~3 GiB)
tre train prepare --recipe recipes/tiny-vi-notes/recipe.yaml
tre train validate --data recipes/tiny-vi-notes/prepared.jsonl
tre train preflight --recipe recipes/tiny-vi-notes/recipe.yaml
tre train run --recipe recipes/tiny-vi-notes/recipe.yaml
```

> Recipe mẫu `tiny-vi-notes` là **fixture kiểm chứng pipeline** (~16 dòng viết tay),
> không phải dữ liệu chất lượng. Adapter sinh ra từ nó không nên dùng thật.

## 4. Quyền riêng tư

- Không tài khoản, không email, không telemetry.
- API chỉ lắng nghe `127.0.0.1`; có kiểm tra Host/Origin cho lệnh ghi.
- Mạng chỉ bị gọi khi bạn `tre models pull` (Hugging Face) hoặc `tre setup`.
- Dữ liệu nằm ở thư mục user-data của hệ điều hành (`~/.local/share/tre-llm` trên Linux),
  đổi được bằng `TRE_LLM_HOME`.

## 5. Giới hạn đã biết (đo thật trên máy dev)

- Model 0.8B thỉnh thoảng trả lời sai kiến thức (xem eval report — giữ nguyên, không che).
- Qwen3.5 mặc định "thinking" — TreLLM đã tắt cho chat thường; bật bằng `tre chat --thinking`.
- GPU offload: chưa kiểm chứng trên máy dev (GTX 1060 chỉ còn ~700 MiB VRAM trống) → không quảng cáo.
- Model 4 GiB RAM trở xuống: chưa có evidence thật → đánh dấu experimental.

## 6. Cấu trúc repo

```
src/tre_llm/        # thư viện Python + server + CLI
apps/web/           # React UI (build → dist/, đóng gói vào wheel)
models/registry/    # registry.yaml — metadata model, checksum, license
evals/tre-viet/     # bộ đánh giá tiếng Việt + SUITE.md
recipes/            # Tre Adapt recipes + dữ liệu fixture
evidence/           # bằng chứng đo thật (smoke, benchmark)
docs/               # kiến trúc, quyết định, báo cáo release
tests/              # 60+ test: protocol + suite integrity + dataprep
```

Xem thêm: [docs/architecture.md](docs/architecture.md) · [docs/support-matrix.md](docs/support-matrix.md) · [docs/troubleshooting.md](docs/troubleshooting.md)
