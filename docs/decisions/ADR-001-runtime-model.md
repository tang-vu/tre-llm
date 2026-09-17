# ADR-001: llama.cpp CPU + Qwen3.5-0.8B cho vertical slice

- Status: accepted, 2026-09-17
- Context: máy dev WSL2, Xeon E5-2678 v3 (AVX2, 48 threads), 31 GiB RAM, GTX 1060 3GB chỉ còn ~763 MiB VRAM trống.
- Decision: runtime chính = llama.cpp b11022 prebuilt ubuntu-x64 (CPU); model đầu tiên = `unsloth/Qwen3.5-0.8B-GGUF` Q4_K_M.
- Alternatives: build llama.cpp từ source (chậm, cần cmake — rejected cho v0.1 nhưng giữ documented build path); llama-cpp-python (kéo CPython binding, fragile — rejected); Ollama (closed binary + ít kiểm soát flag — rejected làm runtime chính).
- Consequences: Qwen3.5 thinking default ON → bắt buộc `chat_template_kwargs.enable_thinking` trong mọi request; cần llama.cpp đủ mới cho arch qwen3.5 (b11022 OK). GPU/Vulkan không test được trên máy này → "not run" trong support matrix.
- Evidence: `evidence/m0-smoke/`, `docs/research.md`.
