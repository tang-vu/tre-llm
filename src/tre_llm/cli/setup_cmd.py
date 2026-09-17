"""`tre setup` — provision runtime binary + chosen model with full disclosure."""

from __future__ import annotations

import os
import platform
import tarfile
import zipfile
from pathlib import Path

import httpx
import typer
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from tre_llm import config, paths
from tre_llm.cli.util import console, die, emit_json
from tre_llm.hardware import collect
from tre_llm.planner.select import build_plan
from tre_llm.registry import catalog, get, installed, pull, sha256_file
from tre_llm.registry.store import Downloader, StoreError, disk_free, hf_resolve_url
from tre_llm.runtimes.llamacpp import find_binary, probe_version
from tre_llm.schemas import Goal
from tre_llm.storage.db import get_db


def _runtime_asset() -> tuple[str, str]:
    """Pick the pinned llama.cpp asset for this OS/arch."""
    rt = config.get("runtime", default={}) or {}
    sysname, machine = platform.system().lower(), platform.machine().lower()
    if sysname == "linux" and machine in ("x86_64", "amd64"):
        return rt.get("ubuntu_x64_url", ""), rt.get("ubuntu_x64_sha256", "")
    if sysname == "windows" and machine in ("amd64", "x86_64"):
        return rt.get("win_x64_url", ""), rt.get("win_x64_sha256", "")
    if sysname == "darwin" and machine == "arm64":
        return rt.get("macos_arm64_url", ""), rt.get("macos_arm64_sha256", "")
    return "", ""


def ensure_runtime(progress: Progress | None = None) -> Path:
    """Return a llama-server path, downloading the pinned build if missing."""
    existing = find_binary()
    if existing:
        return existing
    url, sha = _runtime_asset()
    if not url:
        raise StoreError(
            "Chưa có bản llama.cpp ghim sẵn cho nền tảng này. "
            "Cài llama-server thủ công rồi dùng `tre setup` lại hoặc truyền --runtime-path."
        )
    name = f"llama.cpp-{config.get('runtime', 'llama_cpp_build', default='unknown')}"
    dest_dir = paths.runtimes_dir() / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / Path(url).name

    dl = Downloader()
    task_id = None
    if progress:
        task_id = progress.add_task("llama.cpp runtime", total=None)

        def on_prog(done: int, total: int | None) -> None:
            progress.update(task_id, completed=done, total=total)

        dl.download(url, archive, expected_sha256=sha or None, on_progress=on_prog)
    else:
        dl.download(url, archive, expected_sha256=sha or None)

    # Safe extraction: reject absolute paths and parent escapes.
    def _safe_members(names):
        for n in names:
            p = Path(n)
            if p.is_absolute() or ".." in p.parts:
                raise StoreError(f"Archive không an toàn: {n}")
            yield n

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest_dir, members=list(_safe_members(z.namelist())))
    else:
        with tarfile.open(archive) as t:
            t.extractall(dest_dir, members=list(_safe_members(t.getnames())), filter="data")
    archive.unlink(missing_ok=True)

    for cand in dest_dir.rglob("llama-server"):
        if cand.is_file():
            cand.chmod(cand.stat().st_mode | 0o111)
            return cand
    raise StoreError("Giải nén xong nhưng không thấy llama-server.")


def run(goal: str = "balanced", model_id: str = "", yes: bool = False, json_mode: bool = False) -> None:
    paths.ensure_dirs()
    hw = collect()
    arts = catalog()

    if model_id:
        art = get(model_id)
        if art is None:
            die(f"Model '{model_id}' không có trong registry.")
        from tre_llm.schemas import PlanChoice
        from tre_llm.planner.memory import estimate

        choice = PlanChoice(artifact_id=art.id)
        choice.memory = estimate(art, choice.ctx_size)
    else:
        try:
            g = Goal(goal)
        except ValueError:
            die("--goal phải là light | balanced | quality")
        inst_ids = set(installed())
        plan = build_plan(hw, arts, g, inst_ids)
        if plan.chosen is None:
            die(plan.unsupported_reason or "Không có cấu hình khả thi.")
        choice = plan.chosen
        art = get(choice.artifact_id)
        if art is None:
            die("Kế hoạch chọn model ngoài registry — lỗi nội bộ.")

    total_dl = sum(f.size_bytes for f in art.files)
    runtime_missing = find_binary() is None
    runtime_size = 17 * 2**20 if runtime_missing else 0

    if json_mode:
        emit_json(
            {
                "artifact": art.model_dump(mode="json"),
                "download_bytes": total_dl + runtime_size,
                "runtime_needed": runtime_missing,
                "estimated_peak_ram_mb": choice.memory.total_mb,
                "disk_free_bytes": disk_free(paths.models_dir()),
            }
        )
        if not yes:
            return

    console.print("[bold]TreLLM setup[/bold]")
    t = Table(show_header=False, box=None)
    t.add_column(style="bold")
    t.add_column()
    t.add_row("Model", f"{art.display_name} ({art.upstream_repo}@{art.revision})")
    t.add_row("License", f"{art.license} — {art.license_url or art.source_url}")
    t.add_row("Tải về", f"{(total_dl + runtime_size) / 2**30:.2f} GiB" + (" (gồm runtime)" if runtime_missing else ""))
    t.add_row("RAM ước lượng", f"~{choice.memory.total_mb} MiB ({choice.memory.evidence.value})")
    t.add_row("Disk trống", f"{disk_free(paths.models_dir()) / 2**30:.1f} GiB")
    if art.vietnamese_notes:
        t.add_row("Ghi chú", art.vietnamese_notes.strip())
    console.print(t)

    if not yes:
        typer.confirm("Tiếp tục tải và cài đặt?", abort=True)

    dl = Downloader()
    try:
        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), DownloadColumn(), console=console
        ) as progress:
            binary = ensure_runtime(progress)
            ver = probe_version(binary)
            console.print(f"  llama.cpp {ver.get('build', '?')} tại {binary}")

            tasks: dict[str, object] = {}

            def on_prog(name: str, done: int, total: int | None) -> None:
                tid = tasks.get(name)
                if tid is None:
                    tid = progress.add_task(name, total=total)
                    tasks[name] = tid
                progress.update(tid, completed=done, total=total)

            inst = pull(art, on_progress=on_prog, downloader=dl)
    except KeyboardInterrupt:
        dl.cancel()
        console.print("[yellow]Đã huỷ — giữ .part để resume.[/yellow]")
        raise typer.Exit(130)
    except StoreError as exc:
        die(str(exc))

    get_db().set_setting("active_model", art.id)
    get_db().set_setting("goal", goal)
    console.print(f"\n[green]Sẵn sàng![/green] Model mặc định: {art.id}")
    console.print("Chạy [bold]tre chat[/bold] hoặc [bold]tre serve[/bold] để bắt đầu.")
