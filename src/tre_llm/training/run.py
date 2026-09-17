"""Tre Adapt training runner — real SFT/LoRA via transformers+peft+trl.

Optional heavy deps live in the `train` extra. A CPU tiny-fixture run is a
pipeline test only — it proves parameter update + reload, not model quality.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from tre_llm import config


def _load_recipe(recipe_path: str) -> tuple[dict, Path]:
    p = Path(recipe_path)
    if not p.is_file():
        here = Path(__file__).resolve()
        for parent in here.parents:
            cand = parent / recipe_path
            if cand.is_file():
                p = cand
                break
    if not p.is_file():
        raise FileNotFoundError(f"Không tìm thấy recipe: {recipe_path}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}, p


def run_training(recipe_path: str) -> dict:
    from tre_llm.training.preflight import run_preflight

    pf = run_preflight(recipe_path)
    if not pf["ok"]:
        raise RuntimeError("Preflight thất bại:\n" + "\n".join(pf["lines"]))
    recipe, p = pf["recipe"], Path(pf["recipe_path"])

    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    base = recipe["base_model"]
    seed = int(recipe.get("seed", 42))
    out_dir = Path(recipe.get("output_dir", "training-out")) .resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    data_file = recipe.get("data", {}).get("prepared_file")
    if not data_file or not (p.parent / data_file).is_file():
        raise RuntimeError(f"Thiếu dữ liệu đã chuẩn bị: {data_file} — chạy `tre train prepare` trước.")

    from tre_llm.training.dataprep import validate

    val = validate(p.parent / data_file)
    if not val["ok"]:
        raise RuntimeError("Dữ liệu không đạt validation:\n" + "\n".join(val["issues"]))
    rows = [json.loads(line) for line in (p.parent / data_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    train_frac = float(recipe.get("data", {}).get("train_fraction", 0.9))
    cut = max(1, int(len(rows) * train_frac))
    train_ds = Dataset.from_list(rows[:cut])
    eval_ds = Dataset.from_list(rows[cut:]) if rows[cut:] else None

    # Device: recipe can force cpu (cuda.is_available() is true even with only
    # a few hundred MiB free — not enough for weights).
    force_cpu = recipe.get("device", "auto") == "cpu"
    use_cuda = torch.cuda.is_available() and not force_cpu

    tok = AutoTokenizer.from_pretrained(base)
    dtype = torch.float16 if use_cuda else torch.float32
    model = AutoModelForCausalLM.from_pretrained(base, dtype=dtype)
    model.config.use_cache = False

    lora = recipe.get("lora", {})
    peft_cfg = LoraConfig(
        r=int(lora.get("r", 8)),
        lora_alpha=int(lora.get("alpha", 16)),
        lora_dropout=float(lora.get("dropout", 0.05)),
        target_modules=list(lora.get("targets", ["q_proj", "v_proj"])),
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_cfg)

    max_minutes = float(config.get("budget", "train_max_minutes", default=30))
    sft = recipe.get("sft", {})
    args = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=float(sft.get("epochs", 1)),
        per_device_train_batch_size=int(sft.get("batch_size", 1)),
        gradient_accumulation_steps=int(sft.get("grad_accum", 8)),
        learning_rate=float(sft.get("lr", 2e-4)),
        max_length=int(sft.get("max_length", 512)),
        seed=seed,
        logging_steps=10,
        save_strategy="steps",
        save_steps=int(sft.get("save_steps", 100)),
        report_to=[],
        dataset_text_field=sft.get("text_field", "text"),
        max_time=max_minutes * 60,
        use_cpu=not use_cuda,
    )
    trainer = SFTTrainer(model=model, args=args, train_dataset=train_ds, eval_dataset=eval_ds, processing_class=tok)

    t0 = time.monotonic()
    result = trainer.train()
    minutes = (time.monotonic() - t0) / 60

    adapter_dir = out_dir / "adapter"
    trainer.save_model(str(adapter_dir))
    tok.save_pretrained(str(adapter_dir))

    card = {
        "base_model": base,
        "adapter_dir": str(adapter_dir),
        "train_rows": len(train_ds),
        "eval_rows": len(eval_ds) if eval_ds else 0,
        "minutes": round(minutes, 2),
        "device": "cuda" if use_cuda else "cpu",
        "train_loss": getattr(result, "training_loss", None),
        "seed": seed,
        "recipe": recipe_path,
        "ran_at": datetime.now(UTC).isoformat(),
        "status": "pipeline-smoke" if not use_cuda else "pilot",
    }
    (out_dir / "run-report.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "summary": f"Train xong {minutes:.1f} phút trên {card['device']} — adapter tại {adapter_dir} "
                   f"({'PILOT' if use_cuda else 'PIPELINE SMOKE — không phải cải thiện chất lượng'})",
        "report": card,
    }
