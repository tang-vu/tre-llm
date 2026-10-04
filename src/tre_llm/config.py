"""Load checkout or packaged defaults, with checkout-local overrides."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


def _repo_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "configs" / "defaults.yaml").is_file():
            return parent
    return None


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    root = _repo_root()
    cfg: dict[str, Any] = {}
    if root:
        defaults = root / "configs" / "defaults.yaml"
        local = root / "configs" / "local.yaml"
        if defaults.is_file():
            cfg = yaml.safe_load(defaults.read_text(encoding="utf-8")) or {}
        if local.is_file():
            _deep_merge(cfg, yaml.safe_load(local.read_text(encoding="utf-8")) or {})
    else:
        packaged_defaults = resources.files("tre_llm").joinpath("data/defaults.yaml")
        cfg = yaml.safe_load(packaged_defaults.read_text(encoding="utf-8")) or {}
    return cfg


def _deep_merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def get(*keys: str, default: Any = None) -> Any:
    node: Any = load()
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return node
