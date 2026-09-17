"""llama.cpp runtime adapter.

Owns a supervised `llama-server` subprocess:
launch -> readiness poll -> OpenAI-compatible HTTP -> shutdown/cleanup.

Upstream flags evolve, so the adapter probes `--version` and feature support
instead of assuming a fixed CLI surface.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from tre_llm import paths
from tre_llm.schemas import RuntimeCapabilities


class RuntimeError_(Exception):
    """Launch or supervision failure (named to avoid shadowing RuntimeError)."""


@dataclass
class LaunchConfig:
    model_path: Path
    host: str = "127.0.0.1"
    port: int = 0  # 0 = pick a free loopback port
    ctx_size: int = 4096
    threads: int = 0
    batch_size: int = 512
    ubatch_size: int = 512
    parallel: int = 1
    gpu_layers: int = 0
    flash_attn: str = "auto"
    alias: str = "default"
    extra_args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


def free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def find_binary(explicit: str | None = None) -> Path | None:
    """Locate a llama-server executable: explicit path, PATH, then managed cache."""
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    on_path = shutil.which("llama-server")
    if on_path:
        return Path(on_path)
    rt = paths.runtimes_dir()
    if rt.is_dir():
        for cand in sorted(rt.glob("llama.cpp-*/**/llama-server"), reverse=True):
            if cand.is_file() and os.access(cand, os.X_OK):
                return cand
        for cand in sorted(rt.glob("llama.cpp-*/**/llama-server.exe"), reverse=True):
            if cand.is_file():
                return cand
    return None


def probe_version(binary: Path, timeout: float = 15.0) -> dict[str, str]:
    """Parse `llama-server --version` into build metadata."""
    try:
        out = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        text = (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"raw": "", "error": str(exc)}
    info: dict[str, str] = {"raw": text.strip()}
    m = re.search(r"version:\s*(\S+)", text)
    if m:
        info["version"] = m.group(1)
    m = re.search(r"build\s+(\d+)", text)
    if m:
        info["build"] = f"b{m.group(1)}"
    m = re.search(r"commit\s+([0-9a-f]+)", text)
    if m:
        info["commit"] = m.group(1)
    return info


def probe_devices(binary: Path, timeout: float = 15.0) -> list[str]:
    """Return device descriptions from `--list-devices` (empty list on CPU-only)."""
    try:
        out = subprocess.run(
            [str(binary), "--list-devices"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    devices = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if line and not line.lower().startswith(("available devices", "(none")):
            m = re.match(r"^[^:]+:\s*(.+)$", line)
            devices.append(m.group(1).strip() if m else line)
    return devices


class LlamaCppProcess:
    """Supervised llama-server subprocess with bounded readiness and cleanup."""

    def __init__(self, binary: Path, cfg: LaunchConfig, log_path: Path | None = None) -> None:
        self.binary = binary
        self.cfg = cfg
        self.proc: subprocess.Popen[str] | None = None
        self.base_url = ""
        self.log_path = log_path or (paths.cache_dir() / "llama-server.log")
        self._log_fh = None

    # ------------------------------------------------------------ lifecycle

    def args(self) -> list[str]:
        cfg = self.cfg
        argv = [
            str(self.binary),
            "--model", str(cfg.model_path),
            "--host", cfg.host,
            "--port", str(cfg.port),
            "--ctx-size", str(cfg.ctx_size),
            "--batch-size", str(cfg.batch_size),
            "--ubatch-size", str(cfg.ubatch_size),
            "--parallel", str(cfg.parallel),
            "--alias", cfg.alias,
            "--jinja",
            "--no-webui",
            "--timeout", "300",
        ]
        if cfg.threads:
            argv += ["--threads", str(cfg.threads)]
        if cfg.gpu_layers:
            argv += ["--n-gpu-layers", str(cfg.gpu_layers)]
        if cfg.flash_attn != "auto":
            argv += ["--flash-attn", cfg.flash_attn]
        argv += cfg.extra_args
        return argv

    def start(self, ready_timeout: float = 120.0) -> str:
        if self.proc and self.proc.poll() is None:
            return self.base_url
        cfg = self.cfg
        if cfg.port == 0:
            cfg.port = free_port(cfg.host)
        self.base_url = f"http://{cfg.host}:{cfg.port}"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_fh = open(self.log_path, "ab")  # noqa: SIM115 - held for proc lifetime
        env = os.environ.copy()
        env.update(cfg.env)
        env.setdefault("GGML_CUDA_NO_PINNED", "1")
        try:
            self.proc = subprocess.Popen(
                self.args(),
                stdout=self._log_fh,
                stderr=subprocess.STDOUT,
                env=env,
                text=False,
                # New process group so we can terminate children reliably.
                start_new_session=(os.name != "nt"),
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
        except OSError as exc:
            raise RuntimeError_(f"Không chạy được llama-server: {exc}") from exc

        self._wait_ready(ready_timeout)
        return self.base_url

    def _wait_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        health = f"{self.base_url}/health"
        last_err = ""
        while time.monotonic() < deadline:
            if self.proc and self.proc.poll() is not None:
                tail = self._log_tail()
                raise RuntimeError_(
                    f"llama-server thoát sớm (code {self.proc.returncode}). Log cuối:\n{tail}"
                )
            try:
                r = httpx.get(health, timeout=2.0)
                if r.status_code == 200:
                    return
                last_err = f"health HTTP {r.status_code}"
            except httpx.HTTPError as exc:
                last_err = str(exc)
            time.sleep(0.25)
        self.stop()
        raise RuntimeError_(f"llama-server không sẵn sàng sau {timeout:.0f}s: {last_err}")

    def _log_tail(self, lines: int = 15) -> str:
        try:
            raw = self.log_path.read_bytes()[-8192:]
            return "\n".join(raw.decode("utf-8", "replace").splitlines()[-lines:])
        except OSError:
            return "(không đọc được log)"

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def peak_rss_mb(self) -> float | None:
        """Current RSS of the server process tree (best effort)."""
        try:
            import psutil

            if not self.proc:
                return None
            p = psutil.Process(self.proc.pid)
            total = p.memory_info().rss
            for child in p.children(recursive=True):
                total += child.memory_info().rss
            return total / (1024 * 1024)
        except Exception:
            return None

    def stop(self, timeout: float = 10.0) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                if os.name != "nt":
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        proc.terminate()
                else:
                    proc.terminate()
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    if os.name != "nt":
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError):
                            proc.kill()
                    else:
                        proc.kill()
                    proc.wait(timeout=5)
        finally:
            if self._log_fh:
                with contextlib.suppress(OSError):
                    self._log_fh.close()
                self._log_fh = None

    def __enter__(self) -> LlamaCppProcess:
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


# ------------------------------------------------------------ capabilities


def capabilities(binary: Path | None) -> RuntimeCapabilities:
    caps = RuntimeCapabilities(runtime="llama.cpp")
    if binary is None:
        caps.streaming = caps.cancellation = caps.token_counting = False
        caps.notes.append("llama-server binary not found")
        return caps
    ver = probe_version(binary)
    caps.build = ver.get("build") or ver.get("version", "")
    caps.commit = ver.get("commit", "")
    devices = probe_devices(binary)
    caps.gpu_offload = bool(devices)
    caps.thinking_control = True  # via chat_template_kwargs on supported models
    caps.json_schema_output = True  # llama.cpp supports response_format json_schema
    caps.tool_calling = True
    caps.embeddings = True
    if devices:
        caps.notes.append("devices: " + "; ".join(devices))
    return caps
