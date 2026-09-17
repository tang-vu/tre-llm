# TreLLM — Product Specification (v0.1)

> “LLM tiếng Việt, vừa sức máy bạn.” — Vietnamese AI that fits your machine.

## Người dùng mục tiêu

1. Người dùng phổ thông Việt Nam muốn chạy AI cục bộ trên laptop CPU không GPU.
2. Developer/power user có GPU nhỏ hoặc workstation, cần chọn artifact phù hợp.
3. Người đóng góp OSS muốn thêm model vào registry, thêm eval case, báo cáo phần cứng.

## Workflow chính

`inspect hardware -> identify compatible artifacts -> estimate fit -> bounded calibration -> choose configuration -> Vietnamese tasks -> measure -> reproducible adaptation`

Ba thành phần gắn kết:

- **Tre Fit**: hardware discovery, memory planning, bounded calibration, explainable selection (3 mục tiêu: Nhẹ máy / Cân bằng / Ưu tiên chất lượng), graceful recovery.
- **Tre Viet Lab**: bộ đánh giá hành vi tiếng Việt versioned + đo hiệu năng tái lập + evidence report.
- **Tre Adapt**: chuẩn bị dữ liệu → SFT/LoRA → eval → export → model card, có pilot thật khi tài nguyên cho phép.

Ứng dụng chat cục bộ (CLI + web UI qua `tre serve`) là lớp trình diễn, dùng chung contracts của core library.

## Nguyên tắc trung thực

- Tiny/Lite/Core/Pro là **deployment profile**, không phải model tự train.
- Model upstream giữ nguyên tên, org, revision, license, provenance.
- Adapter tiếng Việt (nếu train) ghi rõ là "TreLLM Vietnamese adaptation of <base model>".
- Measured vs estimated vs unknown phải phân biệt rõ trong mọi output.
- Không mock inference để chứng minh; không bịa benchmark.

## Acceptance gates v0.1 (tóm tắt từ master prompt §5, §19)

1. Python package cài được + CLI `tre`.
2. llama.cpp managed subprocess + attach server ngoài.
3. Hardware inspection, planning, bounded calibration, persistent config.
4. Registry ≥3 size class, phân biệt tested vs documented.
5. ≥1 model thật chạy trên máy dev.
6. Chat streaming tiếng Việt CLI + web app.
7. Subset OpenAI chat API: `GET /health`, `GET /v1/models`, `POST /v1/chat/completions` (stream + non-stream).
8. Document retrieval `.txt`/`.md` với citation kiểm tra được.
9. Eval + performance report tái lập.
10. Training pipeline + tiny tests; pilot thật nếu budget cho phép.
11. Wheel cài được, CI, onboarding song ngữ, release report trung thực.

## Non-goals v0.1

Không pretrain foundation model, không shell/browser agent, không mobile app, TTS/voice/image, K8s, billing/accounts/SaaS, model marketplace, cloud bắt buộc. Không yêu cầu Docker/Node/GPU/API key để chạy bản CPU đã cài.

## Ràng buộc tài nguyên dev (mặc định)

- Không API trả phí / cloud GPU / subscription.
- Tổng tải model mới ≤ 8 GiB; ưu tiên cache đã verify.
- Giữ trống ≥ max(5 GiB, 10% filesystem).
- Chừa ≥ max(1 GiB, 20%) RAM khi plan runtime.
- Calibration ≤120s/candidate, ≤3 candidates; training pilot ≤30 phút active.
- Mọi giới hạn cấu hình được trong `configs/defaults.yaml`.
