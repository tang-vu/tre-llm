"""Runtime manager: translate a plan choice into a running inference server.

Owns the llama-server subprocess, applies the bounded recovery policy, and
hands out a configured ChatClient. Recovery order (max 2 attempts after the
first failure):

1. reduce parallelism/batch
2. reduce context (disclosed)
3. (gpu only) adjust offload
4. caller may substitute a smaller installed artifact
5. stop with a concrete explanation
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from tre_llm.inference.client import ChatClient
from tre_llm.runtimes.llamacpp import (
    LaunchConfig,
    LlamaCppProcess,
    RuntimeError_,
    find_binary,
)
from tre_llm.schemas import PlanChoice

MAX_RECOVERY_ATTEMPTS = 2


@dataclass
class RunningServer:
    client: ChatClient
    process: LlamaCppProcess | None  # None for attached external servers
    base_url: str
    effective: PlanChoice
    adjustments: list[str]

    def stop(self) -> None:
        self.client.close()
        if self.process:
            self.process.stop()


def _launch(binary, choice: PlanChoice, model_path, ready_timeout: float) -> LlamaCppProcess:
    cfg = LaunchConfig(
        model_path=model_path,
        ctx_size=choice.ctx_size,
        threads=choice.threads,
        batch_size=choice.batch_size,
        ubatch_size=choice.ubatch_size,
        parallel=choice.parallel,
        gpu_layers=choice.gpu_layers,
        alias=choice.artifact_id,
    )
    proc = LlamaCppProcess(binary, cfg)
    proc.start(ready_timeout=ready_timeout)
    return proc


def start_managed(
    choice: PlanChoice,
    model_path,
    binary_path: str | None = None,
    ready_timeout: float = 120.0,
    on_adjust=None,
) -> RunningServer:
    """Start an owned llama-server with bounded recovery on launch failure."""
    binary = find_binary(binary_path)
    if binary is None:
        raise RuntimeError_(
            "Không tìm thấy llama-server. Chạy `tre setup` để tải runtime, hoặc "
            "truyền đường dẫn binary với --runtime-path."
        )
    adjustments: list[str] = []
    eff = choice.model_copy(deep=True)
    attempts = 0
    while True:
        proc = None
        try:
            proc = _launch(binary, eff, model_path, ready_timeout)
            base = proc.base_url
            client = ChatClient(base)
            return RunningServer(client, proc, base, eff, adjustments)
        except RuntimeError_ as exc:
            if proc:
                proc.stop()
            attempts += 1
            if attempts > MAX_RECOVERY_ATTEMPTS:
                raise RuntimeError_(
                    f"Không khởi động được model sau {attempts - 1} lần phục hồi. "
                    f"Lỗi cuối: {exc}"
                ) from exc
            if eff.parallel > 1 or eff.batch_size > 256:
                eff.parallel = 1
                eff.batch_size = max(256, eff.batch_size // 2)
                eff.ubatch_size = min(eff.ubatch_size, eff.batch_size)
                msg = f"Giảm parallel/batch (batch={eff.batch_size})"
            elif eff.ctx_size > 2048:
                eff.ctx_size = max(2048, eff.ctx_size // 2)
                msg = f"Giảm context còn {eff.ctx_size} token (ngữ cảnh hội thoại sẽ ngắn hơn)"
            else:
                raise RuntimeError_(
                    f"Không khởi động được model và không còn phương án giảm tải. Lỗi: {exc}"
                ) from exc
            adjustments.append(msg)
            if on_adjust:
                on_adjust(msg)
            time.sleep(0.5)


def start_for_model(
    registry_id: str,
    model_path,
    ctx_override: int = 0,
    on_adjust=None,
    ready_timeout: float = 120.0,
) -> RunningServer:
    """Start a managed server for an explicit installed model — non-CLI helper
    shared by `tre serve` hot-swap and tests (no planner, no die())."""
    from tre_llm import config
    from tre_llm.hardware import collect
    from tre_llm.planner.select import _default_threads

    choice = PlanChoice(artifact_id=registry_id)
    if ctx_override:
        choice.ctx_size = ctx_override
    if not choice.threads:
        choice.threads = _default_threads(collect())
    if not choice.ctx_size:
        choice.ctx_size = int(config.get("defaults", "ctx_size", default=4096))
    return start_managed(choice, model_path, on_adjust=on_adjust, ready_timeout=ready_timeout)


def attach(base_url: str, api_key: str | None = None, timeout: float = 600.0) -> RunningServer:
    """Attach to an explicitly configured external OpenAI-compatible server."""
    client = ChatClient(base_url, timeout=timeout, api_key=api_key)
    if not client.health():
        client.close()
        raise RuntimeError_(f"Không kết nối được server tại {base_url} (health check thất bại)")
    choice = PlanChoice(artifact_id="external")
    return RunningServer(client, None, base_url, choice, [])
