"""`tre serve` — local app: FastAPI API + prebuilt web UI on loopback."""

from __future__ import annotations

from tre_llm.cli.common import start_runtime
from tre_llm.cli.util import console


def run(host: str = "127.0.0.1", port: int = 8471, model: str = "", attach: str = "") -> None:
    import uvicorn

    srv = None
    active = ""
    try:
        srv = start_runtime(model_id=model, attach_url=attach)
        active = srv.effective.artifact_id
        for adj in srv.adjustments:
            console.print(f"[yellow]Phục hồi:[/yellow] {adj}")
    except Exception as exc:
        console.print(f"[yellow]Không khởi động được model ({exc}).[/yellow]")
        console.print("[yellow]Server vẫn mở — UI sẽ hiện đường dẫn setup.[/yellow]")

    from tre_llm.server.app import create_app, mount_static

    app = create_app(server=srv, active_model=active)
    mount_static(app)

    console.print(f"[bold green]TreLLM[/bold green] → http://{host}:{port}  (Ctrl-C để dừng)")
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        if srv:
            srv.stop()
