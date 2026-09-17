"""Shared CLI helpers."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console

console = Console()
err_console = Console(stderr=True)


def emit_json(obj: Any) -> None:
    """Machine-readable JSON to stdout — no progress text mixed in."""
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def die(msg: str, code: int = 1) -> None:
    # SystemExit (not typer.Exit): click 8.5+ may swallow Exit raised inside
    # sub-app commands and return the code as a normal value, yielding exit 0.
    err_console.print(f"[red]Lỗi:[/red] {msg}")
    raise SystemExit(code)


def warn(msg: str) -> None:
    err_console.print(f"[yellow]![/yellow] {msg}")
