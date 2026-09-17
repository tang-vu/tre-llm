"""Filesystem layout for TreLLM user data.

All mutable state lives under platformdirs locations unless TRE_LLM_HOME
overrides the root (useful for tests and portable installs).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir

APP_NAME = "tre-llm"


@lru_cache(maxsize=1)
def home() -> Path:
    """TreLLM data root. Honours TRE_LLM_HOME for tests/dev."""
    override = os.environ.get("TRE_LLM_HOME")
    if override:
        return Path(override).expanduser()
    return Path(user_data_dir(APP_NAME, appauthor=False))


@lru_cache(maxsize=1)
def cache_dir() -> Path:
    override = os.environ.get("TRE_LLM_HOME")
    if override:
        return Path(override).expanduser() / "cache"
    return Path(user_cache_dir(APP_NAME, appauthor=False))


@lru_cache(maxsize=1)
def config_dir() -> Path:
    override = os.environ.get("TRE_LLM_HOME")
    if override:
        return Path(override).expanduser() / "config"
    return Path(user_config_dir(APP_NAME, appauthor=False))


def models_dir() -> Path:
    return cache_dir() / "models"


def runtimes_dir() -> Path:
    return cache_dir() / "runtimes"


def downloads_dir() -> Path:
    return cache_dir() / "downloads"


def eval_results_dir() -> Path:
    return home() / "eval-results"


def reports_dir() -> Path:
    return home() / "reports"


def documents_dir() -> Path:
    return home() / "documents"


def conversations_dir() -> Path:
    return home() / "conversations"


def db_path() -> Path:
    return home() / "tre.db"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def calibration_cache_path() -> Path:
    return cache_dir() / "calibration.json"


def ensure_dirs() -> None:
    for d in (
        home(),
        cache_dir(),
        config_dir(),
        models_dir(),
        runtimes_dir(),
        downloads_dir(),
        eval_results_dir(),
        reports_dir(),
        documents_dir(),
        conversations_dir(),
    ):
        d.mkdir(parents=True, exist_ok=True)


def reset_caches() -> None:
    """Drop memoized dirs — used by tests after changing TRE_LLM_HOME."""
    home.cache_clear()
    cache_dir.cache_clear()
    config_dir.cache_clear()
