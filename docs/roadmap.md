# Roadmap

## v0.1 (đang chạy) — nền móng trung thực

- [x] Tre Fit: inspect → plan → calibrate → recovery
- [x] Registry + download resume/verify sha256
- [x] llama.cpp adapter, SSE streaming, cancel, persist chat
- [x] Documents FTS5 + accentless + citations + injection defense
- [x] Tre Viet suite + deterministic scorers + report
- [x] Tre Adapt prepare/validate/preflight + tiny recipe
- [x] Web UI 5 màn hình
- [ ] Release artifacts + checksum manifest

## v0.2 — chất lượng & phạm vi

- [ ] Verify Lite/Core profiles trên phần cứng thật (cần RAM test)
- [ ] macOS arm64 + Windows native CI
- [ ] PDF text extraction (không OCR) + báo rõ scan-only
- [ ] Judge-model cho rubric items (model lớn hơn chấm model nhỏ)
- [ ] `tre models select` reload nóng (không cần restart serve)

## v0.3 — GPU & adaptation

- [ ] llama.cpp CUDA build + planner offload có kiểm chứng
- [ ] Tre Adapt pilot thật trên GPU đủ VRAM → đo before/after trên tre-viet
- [ ] Xuất adapter → GGUF merge pipeline (llama.cpp convert/quantize)

## Không nằm trong roadmap gần

- Multi-user server / LAN exposure (cần auth trước)
- Tự huấn luyện foundation model (ngoài phạm vi)
- Telemetry opt-in (chỉ cân nhắc khi có nhu cầu thật, mặc định vẫn tắt)
