"""Artifact download / import store.

Guarantees:
- Disk preflight before starting.
- Resumable partial files (HTTP Range when the server supports it).
- Atomic completion: download to `*.part`, verify SHA-256, then rename.
- Integrity reference comes from the registry entry or the HF tree API
  `lfs.oid` — never from a redirect ETag.
- Registry of installed artifacts lives in a small JSON index, separate from
  the SQLite app DB, so a corrupt DB never orphans verified weights.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from tre_llm import paths
from tre_llm.schemas import InstalledModel, ModelArtifact

HF_BASE = "https://huggingface.co"
_CHUNK = 1 << 20  # 1 MiB
MAX_RETRIES = 3
MIN_FREE_BYTES = 5 * 1024**3  # keep >=5 GiB free on target fs


class StoreError(Exception):
    pass


class IntegrityError(StoreError):
    pass


class DownloadCancelled(StoreError):
    pass


def sha256_file(path: Path, on_bytes: Callable[[int], None] | None = None) -> str:
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
            done += len(chunk)
            if on_bytes:
                on_bytes(done)
    return h.hexdigest()


def hf_resolve_url(repo: str, path: str, revision: str = "main") -> str:
    return f"{HF_BASE}/{repo}/resolve/{revision}/{path}"


def hf_tree_sha256(repo: str, path: str, revision: str = "main", client: httpx.Client | None = None) -> str | None:
    """Authoritative LFS SHA-256 for a file in a HF repo, or None."""
    own = client is None
    client = client or httpx.Client(timeout=30)
    try:
        r = client.get(f"{HF_BASE}/api/models/{repo}/tree/{revision}")
        if r.status_code != 200:
            return None
        for entry in r.json():
            if entry.get("path") == path:
                lfs = entry.get("lfs") or {}
                return lfs.get("oid")
        return None
    except httpx.HTTPError:
        return None
    finally:
        if own:
            client.close()


# ------------------------------------------------------------ installed index


def _index_path() -> Path:
    return paths.models_dir() / "installed.json"


def installed() -> dict[str, InstalledModel]:
    p = _index_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, InstalledModel] = {}
    for k, v in data.items():
        try:
            out[k] = InstalledModel.model_validate(v)
        except Exception:
            continue
    return out


def _save_index(idx: dict[str, InstalledModel]) -> None:
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({k: v.model_dump(mode="json") for k, v in idx.items()}, f, indent=2)
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def register(inst: InstalledModel) -> None:
    idx = installed()
    idx[inst.registry_id] = inst
    _save_index(idx)


def unregister(registry_id: str) -> None:
    idx = installed()
    if registry_id in idx:
        del idx[registry_id]
        _save_index(idx)


def disk_free(path: Path) -> int:
    return shutil.disk_usage(path).free


# ------------------------------------------------------------ downloads


class Downloader:
    """Single-file resumable downloader with cancellation."""

    def __init__(self, timeout: float = 60.0):
        self._cancel = threading.Event()
        self._timeout = timeout

    def cancel(self) -> None:
        self._cancel.set()

    def download(
        self,
        url: str,
        dest: Path,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> Path:
        """Download `url` to `dest` atomically. Resumes `dest.part` if present."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")

        if dest.is_file() and expected_sha256 and sha256_file(dest) == expected_sha256:
                if on_progress:
                    on_progress(dest.stat().st_size, dest.stat().st_size)
                return dest

        need = expected_size or 0
        free = disk_free(dest.parent)
        if free - need < MIN_FREE_BYTES:
            raise StoreError(
                f"Không đủ dung lượng: còn {free / 2**30:.1f} GiB, cần ~{need / 2**30:.1f} GiB "
                f"và giữ lại {MIN_FREE_BYTES / 2**30:.0f} GiB trống."
            )

        resume_at = part.stat().st_size if part.is_file() else 0
        headers: dict[str, str] = {}
        if resume_at:
            headers["Range"] = f"bytes={resume_at}-"

        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            if self._cancel.is_set():
                raise DownloadCancelled()
            try:
                with httpx.stream(
                    "GET", url, headers=headers, follow_redirects=True, timeout=self._timeout
                ) as r:
                    if resume_at and r.status_code == 200:
                        # Server ignored Range — restart cleanly.
                        resume_at = 0
                    elif r.status_code not in (200, 206):
                        raise StoreError(f"HTTP {r.status_code} khi tải {url}")
                    total_hdr = r.headers.get("content-length")
                    total = None
                    if total_hdr:
                        total = int(total_hdr) + (resume_at if r.status_code == 206 else 0)
                    elif expected_size:
                        total = expected_size

                    append = bool(resume_at) and r.status_code == 206
                    if not append:
                        resume_at = 0
                    done = resume_at
                    with open(part, "ab" if append else "wb") as f:
                        for chunk in r.iter_bytes(_CHUNK):
                            if self._cancel.is_set():
                                raise DownloadCancelled()
                            f.write(chunk)
                            done += len(chunk)
                            if on_progress:
                                on_progress(done, total)
                    if expected_size and done != expected_size:
                        raise StoreError(f"Thiếu dữ liệu: {done}/{expected_size} bytes")
                    break  # success
            except (httpx.HTTPError, StoreError) as exc:
                if isinstance(exc, StoreError) and "Không đủ" in str(exc):
                    raise
                last_err = exc
                resume_at = part.stat().st_size if part.is_file() else 0
                headers["Range"] = f"bytes={resume_at}-" if resume_at else ""
                headers = {k: v for k, v in headers.items() if v}
                if attempt < MAX_RETRIES:
                    time.sleep(1.5 * (attempt + 1))
        else:
            raise StoreError(f"Tải thất bại sau {MAX_RETRIES + 1} lần: {last_err}")

        if expected_sha256:
            actual = sha256_file(part, None)
            if actual != expected_sha256:
                part.unlink(missing_ok=True)
                raise IntegrityError(
                    f"SHA-256 không khớp cho {dest.name}: kỳ vọng {expected_sha256[:16]}…, "
                    f"nhận {actual[:16]}…. Đã xoá file lỗi."
                )
        os.replace(part, dest)
        return dest


def pull(
    artifact: ModelArtifact,
    on_progress: Callable[[str, int, int | None], None] | None = None,
    verify_online: bool = True,
    downloader: Downloader | None = None,
) -> InstalledModel:
    """Download all files of a registry artifact, verify integrity, register."""
    dl = downloader or Downloader()
    dest_dir = paths.models_dir() / artifact.id
    dest_dir.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(timeout=30) if verify_online else None
    try:
        for f in artifact.files:
            expected = f.sha256 or None
            if not expected and client:
                expected = hf_tree_sha256(artifact.upstream_repo, f.path, artifact.revision, client)
            dest = dest_dir / f.path
            url = hf_resolve_url(artifact.upstream_repo, f.path, artifact.revision)
            dl.download(
                url,
                dest,
                expected_sha256=expected,
                expected_size=f.size_bytes or None,
                on_progress=(lambda n, t, name=f.path: on_progress(name, n, t)) if on_progress else None,
            )
    finally:
        if client:
            client.close()

    inst = InstalledModel(
        registry_id=artifact.id,
        artifact=artifact,
        local_path=str(dest_dir / artifact.files[0].path),
        sha256_actual=sha256_file(dest_dir / artifact.files[0].path),
        installed_at=datetime.now(UTC).isoformat(),
        source="downloaded",
        verified=bool(artifact.files[0].sha256 or verify_online),
    )
    register(inst)
    return inst


def import_local(
    path: Path,
    registry_id: str | None = None,
    move: bool = False,
    provenance: dict[str, str] | None = None,
) -> InstalledModel:
    """Register a local GGUF file without copying unless `move` is set.

    Imported files stay at their original path — ownership stays with the user;
    Tre records the path and hash so a moved/deleted file is detected.
    """
    path = path.expanduser().resolve()
    if not path.is_file():
        raise StoreError(f"Không tìm thấy file: {path}")
    if path.suffix.lower() != ".gguf":
        raise StoreError("Chỉ hỗ trợ import file .gguf")
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise StoreError("File không phải GGUF hợp lệ (magic bytes sai)")

    actual = sha256_file(path)
    rid = registry_id or f"imported-{path.stem.lower().replace(' ', '-')}"

    final = path
    if move:
        dest_dir = paths.models_dir() / rid
        dest_dir.mkdir(parents=True, exist_ok=True)
        final = dest_dir / path.name
        shutil.move(str(path), final)

    inst = InstalledModel(
        registry_id=rid,
        artifact=None,
        local_path=str(final),
        sha256_actual=actual,
        installed_at=datetime.now(UTC).isoformat(),
        source="imported",
        verified=True,  # hash of the file as imported; provenance is the user's
        provenance=provenance or {},
    )
    register(inst)
    return inst


def remove(registry_id: str, delete_files: bool = True) -> bool:
    """Remove an installed model. Downloaded files are deleted; imported files
    are only unregistered unless delete_files=True."""
    idx = installed()
    inst = idx.get(registry_id)
    if not inst:
        return False
    if delete_files or inst.source == "downloaded":
        p = Path(inst.local_path)
        try:
            p.unlink(missing_ok=True)
            # Remove the artifact dir if empty.
            if p.parent != paths.models_dir() and p.parent.is_dir() and not any(p.parent.iterdir()):
                p.parent.rmdir()
        except OSError:
            pass
    unregister(registry_id)
    return True
