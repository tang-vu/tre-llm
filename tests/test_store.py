"""Store: verified downloads, resume, integrity failure, import."""

import hashlib

import pytest

from tre_llm.registry.store import (
    Downloader,
    IntegrityError,
    StoreError,
    import_local,
    installed,
    remove,
    sha256_file,
)


class FakeTransport:
    """Minimal in-process HTTP file server for download tests."""

    def __init__(self, content: bytes, support_range: bool = True):
        self.content = content
        self.support_range = support_range

    def handler(self, request):
        import httpx

        if "range" in request.headers and self.support_range:
            start = int(request.headers["range"].split("=")[1].split("-")[0])
            return httpx.Response(
                206,
                content=self.content[start:],
                headers={"content-length": str(len(self.content) - start)},
            )
        return httpx.Response(
            200, content=self.content, headers={"content-length": str(len(self.content))}
        )


def _dl_with(transport: FakeTransport) -> Downloader:
    import httpx

    dl = Downloader()

    class FakeStream:
        def __init__(self, *a, **k):
            self._resp = None

    # monkeypatch httpx.stream used inside store.download
    import tre_llm.registry.store as store_mod

    orig_stream = httpx.stream

    def fake_stream(method, url, headers=None, follow_redirects=False, timeout=None):
        req = httpx.Request(method, url, headers=headers or {})
        resp = transport.handler(req)

        class Ctx:
            def __enter__(self_):
                return resp

            def __exit__(self_, *a):
                return False

        return Ctx()

    store_mod.httpx.stream = fake_stream
    return dl, orig_stream


def test_download_verify_ok(tmp_path, monkeypatch):
    content = b"GGUF" + b"x" * 10_000
    sha = hashlib.sha256(content).hexdigest()
    dl, orig = _dl_with(FakeTransport(content))
    monkeypatch.setattr("tre_llm.registry.store.MIN_FREE_BYTES", 0)
    try:
        dest = dl.download("https://x/m.gguf", tmp_path / "m.gguf", expected_sha256=sha)
        assert dest.read_bytes() == content
        assert not (tmp_path / "m.gguf.part").exists()
    finally:
        import tre_llm.registry.store as s
        s.httpx.stream = orig


def test_checksum_mismatch_removes_file(tmp_path, monkeypatch):
    dl, orig = _dl_with(FakeTransport(b"corrupt"))
    monkeypatch.setattr("tre_llm.registry.store.MIN_FREE_BYTES", 0)
    try:
        with pytest.raises(IntegrityError):
            dl.download("https://x/m.gguf", tmp_path / "m.gguf", expected_sha256="0" * 64)
        assert not (tmp_path / "m.gguf").exists()
        assert not (tmp_path / "m.gguf.part").exists()
    finally:
        import tre_llm.registry.store as s
        s.httpx.stream = orig


def test_resume_appends_partial(tmp_path, monkeypatch):
    content = b"GGUF" + b"y" * 5000
    sha = hashlib.sha256(content).hexdigest()
    part = tmp_path / "m.gguf.part"
    part.write_bytes(content[:2000])  # simulate interrupted download
    dl, orig = _dl_with(FakeTransport(content))
    monkeypatch.setattr("tre_llm.registry.store.MIN_FREE_BYTES", 0)
    try:
        dest = dl.download("https://x/m.gguf", tmp_path / "m.gguf", expected_sha256=sha)
        assert dest.read_bytes() == content
    finally:
        import tre_llm.registry.store as s
        s.httpx.stream = orig


def test_disk_preflight(tmp_path, monkeypatch):
    monkeypatch.setattr("tre_llm.registry.store.MIN_FREE_BYTES", 10**18)
    dl = Downloader()
    with pytest.raises(StoreError, match="dung lượng"):
        dl.download("https://x/m.gguf", tmp_path / "m.gguf", expected_size=1)


def test_import_local_gguf(tmp_path):
    f = tmp_path / "my model.gguf"
    f.write_bytes(b"GGUF" + b"\x00" * 100)
    inst = import_local(f)
    assert inst.registry_id.startswith("imported-")
    assert inst.source == "imported"
    assert inst.sha256_actual == sha256_file(f)
    assert f.exists()  # not moved


def test_import_rejects_non_gguf(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    with pytest.raises(StoreError):
        import_local(f)


def test_remove_registered(tmp_path):
    f = tmp_path / "m.gguf"
    f.write_bytes(b"GGUFabc")
    inst = import_local(f)
    assert inst.registry_id in installed()
    remove(inst.registry_id, delete_files=False)
    assert inst.registry_id not in installed()
    assert f.exists()  # imported file untouched
