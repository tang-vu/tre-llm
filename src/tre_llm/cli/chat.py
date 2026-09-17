"""`tre chat` — streaming Vietnamese chat REPL over the managed runtime."""

from __future__ import annotations

import uuid

from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from tre_llm import config
from tre_llm.cli.common import start_runtime
from tre_llm.cli.util import console, die, warn
from tre_llm.schemas import GenerationRequest
from tre_llm.storage.db import get_db


def _stream_reply(client, req: GenerationRequest, show_thinking: bool) -> tuple[str, str, dict | None]:
    """Stream one reply; returns (text, reasoning, timings)."""
    text_parts: list[str] = []
    think_parts: list[str] = []
    timings = None
    with Live(Text(""), console=console, refresh_per_second=20, transient=True) as live:
        for ev in client.generate_iter(req):
            if ev.type == "token":
                text_parts.append(ev.text)
                live.update(Text("".join(text_parts)))
            elif ev.type == "reasoning" and show_thinking:
                think_parts.append(ev.text)
                live.update(Text("[suy luận] " + "".join(think_parts)[-400:], style="dim"))
            elif ev.type == "error":
                live.stop()
                die(ev.error)
            elif ev.type == "done":
                timings = ev.timings
    return "".join(text_parts), "".join(think_parts), timings


def run(
    model: str = "",
    server: str = "",
    thinking: bool = False,
    system: str = "",
    ctx: int = 0,
    max_tokens: int = 512,
    once: str = "",
) -> None:
    console.print("[dim]Đang khởi động runtime…[/dim]")
    try:
        srv = start_runtime(model_id=model, attach_url=server, ctx_override=ctx)
    except Exception as exc:
        die(str(exc))
    eff = srv.effective
    for adj in srv.adjustments:
        warn(adj)

    db = get_db()
    conv_id = uuid.uuid4().hex[:12]
    db.create_conversation(conv_id, model_id=eff.artifact_id)
    messages: list[dict[str, str]] = [{"role": "system", "content": system}] if system else []
    if system:
        db.add_message(conv_id, "system", system)

    console.print(
        Panel(
            f"[bold]Model:[/bold] {eff.artifact_id}  •  ctx={eff.ctx_size}  •  "
            f"server={srv.base_url}\n[dim]Gõ /thoát để kết thúc, /mới để mở hội thoại mới, /model <id> để đổi model.[/dim]",
            title="Tre chat",
            border_style="green",
        )
    )

    def ask_once(question: str) -> None:
        nonlocal messages
        messages.append({"role": "user", "content": question})
        db.add_message(conv_id, "user", question)
        req = GenerationRequest(
            model=eff.artifact_id,
            messages=list(messages),
            max_tokens=max_tokens,
            temperature=float(config.get("defaults", "temperature", default=0.7)),
            top_p=float(config.get("defaults", "top_p", default=0.8)),
            top_k=int(config.get("defaults", "top_k", default=20)),
            presence_penalty=float(config.get("defaults", "presence_penalty", default=1.5)),
            enable_thinking=thinking,
        )
        try:
            text, reasoning, timings = _stream_reply(srv.client, req, thinking)
        except KeyboardInterrupt:
            srv.client.cancel()
            console.print("\n[yellow]Đã dừng sinh.[/yellow]")
            return
        console.print(Markdown(text) if text else "[dim](trống)[/dim]")
        if timings and timings.get("predicted_per_second"):
            console.print(
                f"[dim]{timings['predicted_per_second']:.1f} tok/s • "
                f"prompt {timings.get('prompt_per_second', 0):.0f} tok/s[/dim]"
            )
        messages.append({"role": "assistant", "content": text})
        db.add_message(conv_id, "assistant", text, reasoning=reasoning)

    try:
        if once:
            ask_once(once)
            return
        while True:
            try:
                line = console.input("\n[bold green]Bạn:[/bold green] ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line in ("/thoát", "/thoat", "/quit", "/exit"):
                break
            if line == "/mới" or line == "/moi":
                conv_id = uuid.uuid4().hex[:12]
                db.create_conversation(conv_id, model_id=eff.artifact_id)
                messages = [{"role": "system", "content": system}] if system else []
                console.print("[dim]Hội thoại mới.[/dim]")
                continue
            ask_once(line)
    except KeyboardInterrupt:
        console.print("\n[dim]Ctrl-C[/dim]")
    finally:
        console.print("[dim]Đang tắt runtime…[/dim]")
        srv.stop()
