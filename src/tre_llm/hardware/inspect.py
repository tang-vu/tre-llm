"""Resilient hardware discovery.

Every probe is timeout-bounded and returns structured data; a missing tool or
an unrecognized device never crashes the rest of discovery. Unknown values stay
None — we never report a synthetic zero as a measurement.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psutil

from tre_llm.schemas import CpuInfo, DiskInfo, GpuInfo, HardwareSnapshot

PROBE_TIMEOUT = 8.0

# Instruction flags that matter for llama.cpp CPU kernels.
_CPU_FLAG_NAMES = ("avx", "avx2", "avx512f", "avx512_vnni", "fma", "f16c", "sse4_2", "neon", "sve")


def _run(argv: list[str], timeout: float = PROBE_TIMEOUT) -> tuple[int, str]:
    """Run a probe command; never raises. Returns (returncode, stdout)."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout or ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def _cpu_info(errors: list[str]) -> CpuInfo:
    info = CpuInfo(arch=platform.machine().lower())
    try:
        info.logical_cores = psutil.cpu_count(logical=True)
        info.physical_cores = psutil.cpu_count(logical=False)
    except Exception as exc:  # pragma: no cover - platform dependent
        errors.append(f"cpu_count: {exc}")

    system = platform.system()
    if system == "Linux":
        try:
            text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"cpuinfo: {exc}")
        else:
            m = re.search(r"model name\s*:\s*(.+)", text)
            if m:
                info.model = m.group(1).strip()
            flags = set()
            for match in re.finditer(r"^flags\s*:\s*(.+)$", text, re.M):
                flags.update(match.group(1).split())
            info.instruction_sets = sorted(f for f in flags if f in _CPU_FLAG_NAMES)
    elif system == "Darwin":
        rc, out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if rc == 0:
            info.model = out.strip()
        rc, out = _run(["sysctl", "-n", "hw.optional.arm.FEAT_AFP", "hw.optional.AdvSIMD"])
        if "arm" in info.arch:
            info.instruction_sets = ["neon"]
    elif system == "Windows":
        info.model = os.environ.get("PROCESSOR_IDENTIFIER", "").strip()
        # Instruction sets via CPUID are not exposed; record AVX2 via psutil if
        # a future release exposes it. Until then leave unknown.
    if not info.model:
        info.model = platform.processor() or "unknown"
    return info


def _nvidia_gpus(errors: list[str]) -> list[GpuInfo]:
    if not shutil.which("nvidia-smi"):
        return []
    rc, out = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if rc != 0 or not out.strip():
        errors.append(f"nvidia-smi rc={rc}")
        return [GpuInfo(vendor="nvidia", probe_status="error")]
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        gpu = GpuInfo(
            vendor="nvidia",
            model=parts[0],
            driver=parts[3],
            runtime_available=True,
            probe_status="ok",
        )
        try:
            gpu.vram_total_mb = int(float(parts[1]))
            gpu.vram_free_mb = int(float(parts[2]))
        except ValueError:
            pass
        gpus.append(gpu)
    return gpus


def _gpus(errors: list[str]) -> list[GpuInfo]:
    gpus = _nvidia_gpus(errors)
    system = platform.system()
    if system == "Darwin":
        # Apple Silicon reports unified memory; VRAM is shared with RAM.
        chip = ""
        rc, out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if rc == 0:
            chip = out.strip()
        if "arm" in platform.machine().lower() or "Apple" in chip:
            gpus.append(
                GpuInfo(
                    vendor="apple",
                    model=chip or "Apple Silicon",
                    runtime_available=True,
                    unified_memory=True,
                    probe_status="ok",
                )
            )
    elif system == "Linux" and not gpus:
        # Look for AMD/Intel render devices without claiming driver readiness.
        try:
            has_drm = os.path.isdir("/sys/class/drm") and any(
                n.startswith("card") for n in os.listdir("/sys/class/drm")
            )
        except OSError:
            has_drm = False
        if has_drm:
            gpus.append(GpuInfo(vendor="unknown", model="drm device", probe_status="missing_tool"))
    return gpus


def _is_wsl() -> bool:
    if "WSL_DISTRO_NAME" in os.environ:
        return True
    try:
        return "microsoft" in open("/proc/version", encoding="utf-8", errors="replace").read().lower()
    except OSError:
        return False


def _in_container() -> bool:
    if os.path.exists("/.dockerenv") or os.environ.get("container"):  # noqa: SIM112 — env var is lowercase by convention
        return True
    try:
        return any(
            x in Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="replace")
            for x in ("docker", "kubepods", "containerd", "podman")
        )
    except OSError:
        return False


def _cgroup_ram_limit_mb() -> int | None:
    """Container memory limit, if any (None when unlimited)."""
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            raw = Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if raw and raw != "max":
            try:
                val = int(raw)
            except ValueError:
                continue
            # Absurd cgroup defaults mean "no limit".
            if 0 < val < (1 << 60):
                return val // (1024 * 1024)
    return None


def collect() -> HardwareSnapshot:
    """Probe the machine. Never raises; collects probe_errors instead."""
    errors: list[str] = []
    snap = HardwareSnapshot(
        collected_at=datetime.now(UTC).isoformat(),
        os=platform.system().lower(),
        os_version=platform.version(),
        machine=platform.machine(),
        is_wsl=_is_wsl(),
        in_container=_in_container(),
        python_version=platform.python_version(),
    )
    snap.cpu = _cpu_info(errors)

    try:
        mem = psutil.virtual_memory()
        snap.ram_total_mb = int(mem.total / (1024 * 1024))
        snap.ram_available_mb = int(mem.available / (1024 * 1024))
        limit = _cgroup_ram_limit_mb()
        if limit and snap.ram_total_mb and limit < snap.ram_total_mb:
            snap.ram_total_mb = limit
            snap.ram_available_mb = min(snap.ram_available_mb, limit)
    except Exception as exc:
        errors.append(f"memory: {exc}")

    snap.gpus = _gpus(errors)

    seen: set[str] = set()
    for target in {os.getcwd(), str(os.path.expanduser("~"))}:
        try:
            real = os.path.realpath(target)
            if real in seen:
                continue
            seen.add(real)
            usage = shutil.disk_usage(real)
            snap.disks.append(DiskInfo(path=real, free_bytes=usage.free, total_bytes=usage.total))
        except OSError as exc:
            errors.append(f"disk({target}): {exc}")

    snap.probe_errors = errors
    return snap


def fingerprint(snap: HardwareSnapshot) -> str:
    """Short stable fingerprint for calibration cache invalidation."""
    import hashlib
    import json

    payload = {
        "cpu": snap.cpu.model,
        "arch": snap.cpu.arch,
        "phys": snap.cpu.physical_cores,
        "ram": snap.ram_total_mb,
        "gpus": [(g.vendor, g.model, g.vram_total_mb) for g in snap.gpus],
        "os": snap.os,
        "wsl": snap.is_wsl,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
