"""Tre Adapt export — merge LoRA adapter vào base, convert sang GGUF, quantize.

Chuỗi thật: adapter (PEFT) → merged HF dir → convert_hf_to_gguf.py (script
upstream, lấy theo --llama-src) → .gguf f16 → llama-quantize → Q4_K_M.

Provenance không nói dối: model kết quả là base upstream + adapter Tre —
metadata registry ghi rõ cả hai.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from tre_llm import paths


def merge_adapter(base_model: str, adapter_dir: Path, out_dir: Path) -> Path:
    """Merge LoRA adapter vào base model → HF dir mới. Trả về thư mục merged."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    adapter_dir = Path(adapter_dir)
    if not (adapter_dir / "adapter_config.json").is_file():
        raise FileNotFoundError(f"Không thấy adapter_config.json trong {adapter_dir}")

    model = AutoModelForCausalLM.from_pretrained(base_model, dtype=torch.float32)
    model = PeftModel.from_pretrained(model, str(adapter_dir))
    merged = model.merge_and_unload()
    out_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(out_dir, safe_serialization=True)
    AutoTokenizer.from_pretrained(str(adapter_dir)).save_pretrained(out_dir)
    return out_dir


def _find_quantize() -> Path | None:
    rt = paths.runtimes_dir()
    if rt.is_dir():
        for cand in sorted(rt.glob("llama.cpp-*/**/llama-quantize"), reverse=True):
            if cand.is_file() and os.access(cand, os.X_OK):
                return cand
    found = shutil.which("llama-quantize")
    return Path(found) if found else None


def export_gguf(
    adapter_dir: str,
    base_model: str = "",
    out_gguf: str = "",
    quant: str = "Q4_K_M",
    llama_src: str = "",
    keep_f16: bool = False,
) -> dict:
    """Merge adapter + convert + quantize. Trả dict mô tả artifacts."""
    adapter = Path(adapter_dir).resolve()
    cfg = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
    base = base_model or cfg.get("base_model_name_or_path")
    if not base:
        raise RuntimeError("Không xác định được base model — truyền --base.")

    name = Path(out_gguf).stem if out_gguf else f"tre-{adapter.parent.name}-{quant.lower()}"
    work = paths.cache_dir() / "export" / name
    merged_dir = merge_adapter(base, adapter, work / "merged")

    # convert_hf_to_gguf.py là script upstream — không vendor vào repo; lấy từ
    # --llama-src, env TRE_LLAMA_SRC, hoặc cache.
    src = llama_src or os.environ.get("TRE_LLAMA_SRC", "")
    candidates: list[Path] = []
    if src:
        p = Path(src)
        candidates.append(p if p.name == "convert_hf_to_gguf.py" else p / "convert_hf_to_gguf.py")
    candidates += sorted(paths.cache_dir().glob("llama.cpp-*/convert_hf_to_gguf.py"))
    script = next((c for c in candidates if c.is_file()), None)
    if script is None:
        raise RuntimeError(
            "Thiếu convert_hf_to_gguf.py. Tải source llama.cpp đúng build "
            "(https://github.com/ggml-org/llama.cpp/archive/refs/tags/<build>.tar.gz) "
            "rồi truyền --llama-src <thư mục> hoặc đặt TRE_LLAMA_SRC."
        )

    f16 = work / f"{name}-f16.gguf"
    r = subprocess.run(
        [sys.executable, str(script), str(merged_dir), "--outfile", str(f16), "--outtype", "f16"],
        capture_output=True, text=True, cwd=str(script.parent), timeout=3600,
    )
    if r.returncode != 0 or not f16.is_file():
        raise RuntimeError(f"convert_hf_to_gguf lỗi:\n{r.stderr[-2000:]}")

    quantize = _find_quantize()
    if quantize is None:
        raise RuntimeError("Không tìm thấy llama-quantize — chạy `tre setup` trước.")
    out = Path(out_gguf) if out_gguf else work / f"{name}-{quant.lower()}.gguf"
    r = subprocess.run(
        [str(quantize), str(f16), str(out), quant],
        capture_output=True, text=True, timeout=3600,
    )
    if r.returncode != 0 or not out.is_file():
        raise RuntimeError(f"llama-quantize lỗi:\n{r.stderr[-2000:]}")
    if not keep_f16:
        f16.unlink(missing_ok=True)

    card = {
        "gguf": str(out),
        "size_bytes": out.stat().st_size,
        "quant": quant,
        "base_model": base,
        "adapter_dir": str(adapter),
        "provenance": "base upstream + adapter Tre — không phải model pretrain từ đầu",
        "exported_at": datetime.now(UTC).isoformat(),
    }
    (out.parent / f"{name}-export.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return card
