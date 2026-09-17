"""Runtime adapter contract.

A runtime adapter owns (or attaches to) an inference server speaking the
OpenAI-compatible HTTP surface. The control plane never links against the
inference engine directly.
"""

from __future__ import annotations

from typing import Protocol

from tre_llm.schemas import RuntimeCapabilities


class RuntimeHandle:
    """A launched or attached runtime."""

    def __init__(self, base_url: str, pid: int | None, owned: bool) -> None:
        self.base_url = base_url
        self.pid = pid
        self.owned = owned


class RuntimeAdapter(Protocol):
    name: str

    def capabilities(self) -> RuntimeCapabilities: ...
    def is_available(self) -> bool: ...
