"""`tre doctor` — read-only environment and readiness check."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from tre_llm import paths
from tre_llm.cli.util import console, emit_json
from tre_llm.hardware import collect, fingerprint
from tre_llm.registry import catalog, installed
from tre_llm.runtimes.llamacpp import capabilities, find_binary, probe_version
from tre_llm.storage.db import get_db
from tre_llm.version import __version__


def _fixes(snap, binary, inst, calib) -> list[str]:
    fixes: list[str] = []
    if binary is None:
        fixes.append("Chạy `tre setup` để tải llama.cpp runtime đã ghim phiên bản.")
    if not inst:
        fixes.append("Chạy `tre models list` rồi `tre models pull <id>` để tải một model.")
    if snap.ram_total_mb is not None and snap.ram_total_mb < 3072:
        fixes.append("RAM < 3 GiB: chỉ nên dùng profile Tiny với ngữ cảnh nhỏ.")
    if not calib and inst:
        fixes.append("Chạy `tre bench --quick` để hiệu chuẩn hiệu năng thực trên máy này.")
    if not fixes:
        fixes.append("Mọi thứ sẵn sàng — `tre chat` để bắt đầu.")
    return fixes


def run(json_mode: bool = False) -> None:
    paths.ensure_dirs()
    snap = collect()
    binary = find_binary()
    inst = installed()
    reg = catalog()

    calib: dict = {}
    try:
        from tre_llm.planner.calibrate import load_cache

        calib = load_cache()
    except Exception:
        pass

    if json_mode:
        emit_json(
            {
                "schema_version": 1,
                "tre_version": __version__,
                "hardware": snap.model_dump(mode="json"),
                "hardware_fingerprint": fingerprint(snap),
                "runtime_binary": str(binary) if binary else None,
                "runtime": probe_version(binary) if binary else None,
                "capabilities": capabilities(binary).model_dump(mode="json"),
                "installed_models": {k: v.local_path for k, v in inst.items()},
                "registry_size": len(reg),
                "calibration_entries": len(calib),
                "fixes": _fixes(snap, binary, inst, calib),
            }
        )
        return

    console.print(Panel.fit(f"[bold green]TreLLM[/bold green] v{__version__} — kiểm tra hệ thống", border_style="green"))

    t = Table(show_header=False, box=None, pad_edge=False)
    t.add_column(style="bold")
    t.add_column()
    t.add_row("Hệ điều hành", f"{snap.os} ({'WSL2' if snap.is_wsl else 'native'}{', container' if snap.in_container else ''})")
    cpu_bits = ",".join(snap.cpu.instruction_sets) or "?"
    t.add_row("CPU", f"{snap.cpu.model} — {snap.cpu.physical_cores}C/{snap.cpu.logical_cores}T [{cpu_bits}]")
    t.add_row(
        "RAM",
        f"{snap.ram_total_mb} MiB tổng, {snap.ram_available_mb} MiB khả dụng"
        if snap.ram_total_mb
        else "không đo được",
    )
    for g in snap.gpus:
        t.add_row(
            "GPU",
            f"{g.vendor} {g.model} — VRAM {g.vram_free_mb}/{g.vram_total_mb} MiB trống"
            + ("" if g.runtime_available else " (driver chưa sẵn sàng)"),
        )
    if not snap.gpus:
        t.add_row("GPU", "không phát hiện (chế độ CPU)")
    for d in snap.disks:
        t.add_row("Disk", f"{d.path}: {d.free_bytes / 2**30:.1f} GiB trống / {d.total_bytes / 2**30:.0f} GiB")
    if snap.probe_errors:
        t.add_row("[yellow]Probe lỗi[/yellow]", "; ".join(snap.probe_errors[:3]))
    console.print(t)

    rt = Table(show_header=False, box=None)
    rt.add_column(style="bold")
    rt.add_column()
    if binary:
        ver = probe_version(binary)
        rt.add_row("llama.cpp", f"{ver.get('build', '?')} ({ver.get('commit', '')[:9]}) tại {binary}")
    else:
        rt.add_row("llama.cpp", "[red]chưa có[/red]")
    rt.add_row("Registry", f"{len(reg)} artifact")
    rt.add_row("Model đã cài", ", ".join(inst) if inst else "chưa có")
    rt.add_row("Calibration", f"{len(calib)} kết quả đã lưu")
    console.print(rt)

    console.print("[bold]Gợi ý:[/bold]")
    for f in _fixes(snap, binary, inst, calib):
        console.print(f"  • {f}")
