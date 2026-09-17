# Changelog

## v0.1.0 — chưa phát hành (trunk)

### Thêm

- `tre` CLI: doctor / plan / setup / models {list,pull,import,remove} / chat /
  serve / ask / eval / bench / report / train {prepare,validate,preflight,run}
- Tre Fit: hardware inspect (CPU/RAM/GPU/disk/WSL/container), memory planner
  hiểu hybrid architecture, calibration bounded + cache fingerprint, recovery ≤2
- Registry 4 profile với sha256 thật; download resume + verify + atomic
- llama.cpp b11022 adapter: health, stream SSE, cancel, timings, process ownership
- FastAPI: `/v1/chat/completions` (OpenAI subset) + `/api/*`; loopback + host/origin guard
- Documents: .txt/.md, FTS5 accentless, citations, deletion, injection defense
- Tre Viet Lab: 22 items (5 dev / 17 test), deterministic + rubric-ungraded
- Tre Adapt: manifest→prepare→validate(leakage)→preflight→LoRA run (pipeline)
- Web UI React: Máy / Trò chuyện / Tài liệu / Phòng thử / Mô hình

### Evidence (máy dev: Xeon E5-2678 v3, 31 GiB, CPU-only)

- Qwen3.5-0.8B-Q4_K_M: 21 tok/s decode, 124 tok/s prompt, RSS 904 MiB
- Tre Viet test: 14 graded, pass 0.714 (có câu sai thật, giữ nguyên)
- Injection trong tài liệu: không bị lừa
- 63 unit/protocol tests pass

### Đã biết / giới hạn

- GPU path chưa kiểm chứng (VRAM trống không đủ trên máy dev)
- `tre train run` chưa chạy pilot thật — chỉ pipeline được test
- PDF scan chưa hỗ trợ (báo "cần OCR" rõ ràng)
