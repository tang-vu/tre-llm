# Tre Viet — bộ đánh giá tiếng Việt v0.1

## Mục tiêu

Đo **hành vi thực dụng** của model trên tiếng Việt, không phải benchmark học thuật.
Mỗi item ghi rõ `provenance` và `grading.kind`. Item rubric KHÔNG được chấm tự động
trừ khi cấu hình judge model riêng — `score=null` là trung thực, không phải lỗi.

## Cấu trúc file

| File | Category | Kỹ năng đo | Grader chính |
|------|----------|-----------|--------------|
| `qna.jsonl` | `qna` | Hỏi đáp thực tế, số học đơn giản | `contains`, `numeric` |
| `extract.jsonl` | `extract` | Trích xuất cấu trúc từ văn bản | `json_schema` |
| `notes.jsonl` | `notes` | Ghi chú học tập, tóm tắt | `rubric` (ungraded) |
| `docs.jsonl` | `docs` | Kỷ luật trích dẫn, chống prompt-injection | `citation_exists`, `refusal`, `contains` |

## Splits

- `dev`: 5 items — dùng để iterate prompt/pipeline. **Không** dùng để báo cáo kết quả.
- `test`: 17 items — held-out. Mọi số liệu công bố phải chạy trên `test`.

Leakage được kiểm tra trong `tests/test_suite.py`: prompt của item `test` không được
xuất hiện (sau khi fold dấu + lowercase) trong bất kỳ item `dev` nào và ngược lại,
cũng như không được trùng trong `recipes/**/data` (dữ liệu train).

## Provenance

- `curated`: câu hỏi viết tay cho dự án này bởi maintainer, CC-BY-4.0.
- `synthetic`: sinh theo template có kiểm soát, CC-BY-4.0.
- Không dùng dữ liệu crawl chưa rõ license trong v0.1.

## Cách chạy

```bash
tre eval --suite tre-viet --split dev --limit 3     # smoke nhanh
tre eval --suite tre-viet --split test              # baseline đầy đủ (chậm trên CPU)
tre report --format html                            # tổng hợp evidence
```

## Giới hạn đã biết

- Grader `contains` fold dấu → không phân biệt được lỗi chính tả dấu.
- Item rubric cần judge model hoặc chấm tay — chưa có trong v0.1.
- Suite nhỏ (22 items) → chỉ đủ phát hiện regression thô, không phải điểm chất lượng tuyệt đối.
- Baseline dev đã đo thật trên Qwen3.5-0.8B-Q4_K_M: 4 graded, mean 0.625 — có câu sai thật (52 tuần→trả lời 12), được giữ nguyên trong report.
