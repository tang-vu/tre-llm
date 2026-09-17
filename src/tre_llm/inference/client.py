"""OpenAI-compatible inference client with streaming + cancellation.

Speaks to a running llama-server (owned or attached). Parses SSE frames into
`GenerationEvent`s, propagates cancellation by aborting the HTTP request, and
captures llama.cpp `timings` blocks for measurement.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from tre_llm.schemas import GenerationEvent, GenerationRequest


class InferenceError(Exception):
    pass


class Cancelled(InferenceError):
    pass


@dataclass
class GenerationResult:
    text: str = ""
    reasoning: str = ""
    finish_reason: str = ""
    usage: dict[str, Any] | None = None
    timings: dict[str, Any] | None = None
    ttft_ms: float | None = None
    total_ms: float | None = None
    cancelled: bool = False
    error: str = ""
    events: list[GenerationEvent] = field(default_factory=list)


def _payload(req: GenerationRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": req.model or "default",
        "messages": req.messages,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "presence_penalty": req.presence_penalty,
        "stream": req.stream,
    }
    if req.stop:
        body["stop"] = req.stop
    if req.enable_thinking is not None:
        # Qwen3.x chat templates honour enable_thinking via template kwargs.
        body["chat_template_kwargs"] = {"enable_thinking": req.enable_thinking}
    return body


def _parse_delta(delta: dict[str, Any]) -> tuple[str, str]:
    """Extract (content, reasoning) from a streamed delta."""
    content = delta.get("content") or ""
    reasoning = delta.get("reasoning_content") or ""
    return content, reasoning


class ChatClient:
    def __init__(self, base_url: str, timeout: float = 600.0, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cancel = threading.Event()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------ endpoints

    def health(self) -> bool:
        try:
            r = self._client.get(f"{self.base_url}/health", timeout=5.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def models(self) -> list[dict[str, Any]]:
        r = self._client.get(f"{self.base_url}/v1/models", timeout=10.0)
        r.raise_for_status()
        return r.json().get("data", [])

    def tokenize(self, text: str) -> list[int] | None:
        """Token ids when the server supports /tokenize; else None."""
        try:
            r = self._client.post(
                f"{self.base_url}/tokenize", json={"content": text}, timeout=15.0
            )
            if r.status_code != 200:
                return None
            data = r.json()
            tokens = data.get("tokens")
            return tokens if isinstance(tokens, list) else None
        except httpx.HTTPError:
            return None

    def count_tokens(self, text: str) -> int | None:
        toks = self.tokenize(text)
        return len(toks) if toks is not None else None

    # ------------------------------------------------------------ generation

    def cancel(self) -> None:
        self._cancel.set()

    def generate(self, req: GenerationRequest) -> GenerationResult:
        """Blocking generate; returns full result. Always streams internally so
        TTFT is honest and cancellation propagates to the server."""
        result = GenerationResult()
        for _ in self._stream(req, result):
            pass
        return result

    def generate_iter(self, req: GenerationRequest) -> Iterator[GenerationEvent]:
        """Yield GenerationEvents for a request; honours cancel()."""
        result = GenerationResult()
        yield from self._stream(req, result)

    def _stream(self, req: GenerationRequest, result: GenerationResult) -> Iterator[GenerationEvent]:
        self._cancel.clear()
        body = _payload(req)
        body["stream"] = True  # always stream; callers see the same contract
        t_start = time.monotonic()

        try:
            with self._client.stream(
                "POST", f"{self.base_url}/v1/chat/completions", json=body
            ) as r:
                if r.status_code != 200:
                    detail = r.read().decode("utf-8", "replace")[:2000]
                    result.error = f"HTTP {r.status_code}: {detail}"
                    yield GenerationEvent(type="error", error=result.error)
                    return
                for line in r.iter_lines():
                    if self._cancel.is_set():
                        result.cancelled = True
                        r.close()
                        yield GenerationEvent(type="done", finish_reason="cancelled")
                        return
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if result.ttft_ms is None:
                        result.ttft_ms = (time.monotonic() - t_start) * 1000
                    for choice in chunk.get("choices", []):
                        content, reasoning = _parse_delta(choice.get("delta", {}))
                        if choice.get("finish_reason"):
                            result.finish_reason = choice["finish_reason"]
                        if reasoning:
                            result.reasoning += reasoning
                            ev = GenerationEvent(type="reasoning", text=reasoning)
                            result.events.append(ev)
                            yield ev
                        if content:
                            result.text += content
                            ev = GenerationEvent(type="token", text=content)
                            result.events.append(ev)
                            yield ev
                    if chunk.get("usage"):
                        result.usage = chunk["usage"]
                    if chunk.get("timings"):
                        result.timings = chunk["timings"]
        except httpx.HTTPError as exc:
            if self._cancel.is_set():
                result.cancelled = True
                yield GenerationEvent(type="done", finish_reason="cancelled")
                return
            result.error = str(exc)
            yield GenerationEvent(type="error", error=result.error)
            return
        result.total_ms = (time.monotonic() - t_start) * 1000
        ev = GenerationEvent(
            type="done",
            finish_reason=result.finish_reason or "stop",
            usage=result.usage,
            timings=result.timings,
        )
        result.events.append(ev)
        yield ev
