"""`tre models …` — registry browsing, verified pulls, local import."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from tre_llm import paths
from tre_llm.cli.util import console, die, emit_json
from tre_llm.registry import catalog, get, import_local, installed, pull, remove
from tre_llm.registry.store import Downloader
from tre_llm.schemas import Evidence

app = typer.Typer(no_args_is_help=True)

EVIDENCE_VI = {
    Evidence.MEASURED: "[green]đã test[/green]",
    Evidence.ESTIMATED: "[yellow]ước lượng[/yellow]",
    Evidence.DOCUMENTED: "[blue]tài liệu[/blue]",
    Evidence.UNKNOWN: "[dim]chưa rõ[/dim]",
}


@app.command("list", help="Liệt kê registry + trạng thái cài đặt.")
def list_(json: bool = typer.Option(False, "--json")) -> None:
    arts = catalog()
    inst = installed()
    if json:
        emit_json(
            {
                "registry": [a.model_dump(mode="json") for a in arts],
                "installed": {k: v.model_dump(mode="json") for k, v in inst.items()},
            }
        )
        return
    t = Table(title="Model registry (upstream thật)")
    t.add_column("ID")
    t.add_column("Profile")
    t.add_column("Upstream")
    t.add_column("Quant")
    t.add_column("Size")
    t.add_column("License")
    t.add_column("Bằng chứng")
    t.add_column("Đã cài")
    for a in arts:
        size = sum(f.size_bytes for f in a.files) / 2**30
        t.add_row(
            a.id,
            a.profile,
            a.upstream_repo,
            a.quantization,
            f"{size:.2f} GiB",
            a.license,
            EVIDENCE_VI[a.evidence],
            "[green]✓[/green]" if a.id in inst else "",
        )
    console.print(t)
    imported = [v for k, v in inst.items() if v.source == "imported"]
    if imported:
        console.print("[bold]Import cục bộ:[/bold]")
        for v in imported:
            console.print(f"  • {v.registry_id}: {v.local_path}")


@app.command("pull", help="Tải model từ registry (resume + verify SHA-256).")
def pull_(
    artifact_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "-y", "--yes"),
) -> None:
    art = get(artifact_id)
    if art is None:
        die(f"Không có '{artifact_id}' trong registry. Xem `tre models list`.")
    inst = installed()
    if artifact_id in inst:
        console.print(f"[green]Đã cài:[/green] {inst[artifact_id].local_path}")
        return
    total = sum(f.size_bytes for f in art.files)
    console.print(
        f"Tải [bold]{art.display_name}[/bold] từ {art.upstream_repo}\n"
        f"  {total / 2**30:.2f} GiB • license {art.license} • nguồn {art.source_url}"
    )
    if not yes:
        typer.confirm("Tiếp tục tải?", abort=True)

    dl = Downloader()
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            console=console,
        ) as progress:
            tasks: dict[str, object] = {}

            def on_prog(name: str, done: int, total_b: int | None) -> None:
                tid = tasks.get(name)
                if tid is None:
                    tid = progress.add_task(name, total=total_b)
                    tasks[name] = tid
                progress.update(tid, completed=done, total=total_b)

            inst_model = pull(art, on_progress=on_prog, downloader=dl)
    except KeyboardInterrupt:
        dl.cancel()
        console.print("[yellow]Đã huỷ — file .part được giữ để resume lần sau.[/yellow]")
        raise typer.Exit(130)
    except Exception as exc:
        die(str(exc))
    console.print(f"[green]Xong.[/green] {inst_model.local_path}\n  sha256={inst_model.sha256_actual}")


@app.command("import", help="Đăng ký file .gguf có sẵn (không copy mặc định).")
def import_(
    path: Path = typer.Argument(..., exists=True),
    registry_id: str = typer.Option("", "--id", help="id tuỳ chọn"),
    move: bool = typer.Option(False, "--move", help="Chuyển file vào cache của Tre."),
) -> None:
    try:
        inst = import_local(path, registry_id or None, move=move)
    except Exception as exc:
        die(str(exc))
    console.print(f"[green]Đã import:[/green] {inst.registry_id} → {inst.local_path}")
    console.print(f"  sha256={inst.sha256_actual}")


@app.command("remove", help="Gỡ model đã cài.")
def remove_(
    artifact_id: str = typer.Argument(...),
    keep_files: bool = typer.Option(False, "--keep-files", help="Chỉ bỏ đăng ký."),
) -> None:
    if not remove(artifact_id, delete_files=not keep_files):
        die(f"Model '{artifact_id}' chưa cài.")
    console.print(f"[green]Đã gỡ {artifact_id}.[/green]")
