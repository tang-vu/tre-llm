# Contributing

## Nguyên tắc bất biến

- **Không bịa số liệu.** Mọi benchmark/đo lường phải có lệnh + môi trường + artifact.
- **Không mock làm bằng chứng.** Fake-runtime tests là protocol tests; evidence inference phải chạy model thật.
- **Giữ danh tính upstream.** Không đổi tên model upstream thành "Tre model".
- Mọi giá trị measured/estimated/unknown/documented phải gắn nhãn đúng.

## Dev setup

```bash
uv sync --all-extras      # hoặc không --all-extras nếu không cần train
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src tests
cd apps/web && npm install && npm run build
```

## Quy ước

- Commit: conventional-ish, tiếng Việt hoặc Anh đều OK, nói "why" không chỉ "what".
- Python: ruff format/check, mypy soft-strict. File > ~200 dòng: cân nhắc tách module.
- UI: không innerHTML; markdown render qua `src/markdown.tsx` (structural sanitizer).
- Thêm model vào registry: phải có sha256 thật (lấy từ HF `lfs.oid`), license, source_url.
- Thêm eval item: ghi `provenance`, `license`, `split`, grader deterministic khi có thể.

## Test yêu cầu khi thay đổi

- Planner/download/runtime: thêm unit test.
- Thay đổi API: chạy `tests/test_api.py` + `tests/test_tre_api.py`.
- Thay đổi eval/training data: `tests/test_suite.py` + `tests/test_dataprep.py` phải pass (leakage).
- Integration test (model thật) chạy riêng: `pytest -m integration`.
