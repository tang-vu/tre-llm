"""Checkout defaults and local overrides must retain their existing precedence."""

from tre_llm import config


def test_checkout_defaults_and_local_overrides(tmp_path, monkeypatch):
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "defaults.yaml").write_text(
        "runtime:\n  llama_cpp_build: pinned\n  ubuntu_x64_url: https://example.test/runtime\n",
        encoding="utf-8",
    )
    (configs / "local.yaml").write_text("runtime:\n  llama_cpp_build: local\n", encoding="utf-8")
    monkeypatch.setattr(config, "_repo_root", lambda: tmp_path)
    config.load.cache_clear()
    try:
        assert config.get("runtime", "llama_cpp_build") == "local"
        assert config.get("runtime", "ubuntu_x64_url") == "https://example.test/runtime"
    finally:
        config.load.cache_clear()
