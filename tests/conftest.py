import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets an isolated TRE_LLM_HOME so caches/DB never leak."""
    home = tmp_path / "tre-home"
    home.mkdir()
    monkeypatch.setenv("TRE_LLM_HOME", str(home))
    from tre_llm import paths
    from tre_llm.storage import db as dbmod

    paths.reset_caches()
    paths.ensure_dirs()
    yield home
    dbmod.reset_default()
    paths.reset_caches()
