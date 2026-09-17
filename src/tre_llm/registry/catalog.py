"""Curated registry loading and lookup."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path

import yaml

from tre_llm.schemas import ModelArtifact


def _registry_path() -> Path | None:
    """Locate registry.yaml — package data first, then source checkout."""
    try:
        res = resources.files("tre_llm.data.registry").joinpath("registry.yaml")
        p = Path(str(res))
        if p.is_file():
            return p
    except (ImportError, TypeError, FileNotFoundError):
        pass
    # Source checkout fallback: <repo>/models/registry/registry.yaml
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "models" / "registry" / "registry.yaml"
        if cand.is_file():
            return cand
    return None


@lru_cache(maxsize=1)
def catalog() -> list[ModelArtifact]:
    path = _registry_path()
    if path is None:
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [ModelArtifact.model_validate(a) for a in data.get("artifacts", [])]


def get(artifact_id: str) -> ModelArtifact | None:
    for a in catalog():
        if a.id == artifact_id:
            return a
    return None


def by_profile(profile: str) -> list[ModelArtifact]:
    return [a for a in catalog() if a.profile == profile]


def clear_cache() -> None:
    catalog.cache_clear()
