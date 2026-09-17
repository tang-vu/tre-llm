# TreLLM

**LLM tiếng Việt, vừa sức máy bạn.** — Vietnamese local AI that fits your machine.

TreLLM chạy mô hình ngôn ngữ địa phương tiếng Việt trên phần cứng bạn thật sự có —
không cần GPU đắt tiền, không gửi dữ liệu ra ngoài — với bằng chứng đo lường trung thực
về những gì hoạt động và những gì không.

> TreLLM **không tự huấn luyện** các model trong registry. Model upstream giữ nguyên
> tên, nhà phát hành, license và checksum gốc. `Tiny/Lite/Core/Pro` là *profile triển
> khai*, không phải tên model riêng.

## Cài đặt nhanh

```bash
# Yêu cầu: Python 3.11/3.12, ~4 GiB RAM trống, ~3 GiB disk
uv sync                      # hoặc: pip install -e .
tre doctor                   # kiểm tra phần cứng (read-only)
tre setup                    # tải runtime + model theo kế hoạch đề xuất
tre chat                     # chat streaming tiếng Việt
tre serve                    # web UI + API tại http://127.0.0.1:8471
```

Xem [docs/install.md](docs/install.md) cho cài chi tiết và [README.vi.md](README.vi.md)
cho hướng dẫn tiếng Việt đầy đủ.

## Thành phần

| Thành phần | Vai trò |
|-----------|---------|
| **Tre Fit** | Quét phần cứng → ước lượng bộ nhớ bảo thủ → chọn model/runtime có giải thích → hiệu chuẩn có giới hạn |
| **Tre Viet Lab** | Bộ đánh giá tiếng Việt với provenance, split dev/test, grader deterministic; báo cáo evidence |
| **Tre Adapt** | Chuẩn bị + validate dữ liệu SFT (leakage check), preflight, LoRA recipe, xuất trung thực |
| **`tre` CLI** | doctor / plan / setup / models / chat / serve / ask / eval / bench / report / train |
| **Web UI** | 5 màn hình (Máy · Trò chuyện · Tài liệu · Phòng thử · Mô hình), cùng contract với API |
| **Local API** | Loopback-only FastAPI: `/v1/chat/completions` (OpenAI subset có chủ đích) + `/api/*` |

## Bằng chứng thật đã đo

Trên máy dev (Xeon E5-2678 v3, 31 GiB RAM, CPU-only, llama.cpp b11022,
`unsloth/Qwen3.5-0.8B-GGUF` Q4_K_M):

- Decode ~21 tok/s, prompt ~124 tok/s, peak RSS ~904 MiB — `evidence/m0-m1/SMOKE.md`
- Tre Viet test split: 14 câu chấm tự động, pass rate 0.714 — **có câu sai thật,
  được giữ nguyên** (model 0.8B trả lời sai câu không dấu, sai số tuần/năm)
- Prompt injection trong tài liệu: không bị lừa (đã đo)

## Nguyên tắc

1. **Trung thực** — measured/estimated/unknown/documented luôn gắn nhãn; không bịa benchmark.
2. **Cục bộ** — inference chạy trên máy bạn; mạng chỉ dùng để tải model khi bạn yêu cầu.
3. **Vừa sức** — chọn cấu hình vừa phần cứng, từ chối rõ ràng khi không khả thi.

## License

Apache-2.0 — xem [LICENSE](LICENSE) (nếu có) và [docs/provenance.md](docs/provenance.md)
cho license của từng model upstream.
