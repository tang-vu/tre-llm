"""Tre Adapt preflight: validate recipe, paths, data manifest, and resources."""

from __future__ import annotations

from pathlib import Path

import yaml

from tre_llm import paths
from tre_llm.hardware import collect


def run_preflight(recipe_path: str) -> dict:
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
    recipe = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    lines: list[str] = [f"Recipe: {p.name}"]
    ok = True

    # deps
    try:
        import torch  # noqa: F401

        lines.append(f"  torch {torch.__version__} — cuda={torch.cuda.is_available()}")
    except ImportError:
        lines.append("  [THIẾU] torch — cài `uv pip install 'tre-llm[train]'`")
        ok = False
    for mod in ("transformers", "peft", "trl", "datasets"):
        try:
            __import__(mod)
            lines.append(f"  {mod} OK")
        except ImportError:
            lines.append(f"  [THIẾU] {mod}")
            ok = False

    # base model
    base = recipe.get("base_model", "")
    lines.append(f"  base: {base or '[THIẾU base_model]'}")
    if not base:
        ok = False

    # data manifest
    data = recipe.get("data", {})
    manifest = data.get("manifest", "")
    mpath = p.parent / manifest if manifest else None
    if not manifest or not (mpath and mpath.is_file()):
        lines.append(f"  [THIẾU] data manifest: {manifest or '(không khai báo)'}")
        ok = False
    else:
        m = yaml.safe_load(mpath.read_text(encoding="utf-8")) or {}
        n = len(m.get("sources", []))
        lines.append(f"  manifest: {n} nguồn dữ liệu, license kiểm tra ở manifest")
        if n == 0:
            ok = False

    # resources
    hw = collect()
    est_vram = recipe.get("est_vram_gb", 0)
    if hw.gpus and any(g.runtime_available for g in hw.gpus):
        free = min((g.vram_free_mb or 0) for g in hw.gpus if g.runtime_available)
        if est_vram and free < est_vram * 1024:
            lines.append(f"  [CẢNH BÁO] VRAM trống {free} MiB < ước lượng {est_vram} GiB")
            ok = False
    else:
        lines.append("  Không có GPU khả dụng → chỉ CPU smoke test (pipeline check, KHÔNG phải quality training).")
    if (hw.ram_available_mb or 0) < 4096:
        lines.append(f"  [CẢNH BÁO] RAM trống {hw.ram_available_mb} MiB thấp")

    return {"ok": ok, "lines": lines, "recipe": recipe, "recipe_path": str(p)}
