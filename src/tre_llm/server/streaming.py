"""Keep generation ownership until the response and its sync iterator stop."""

from __future__ import annotations

import threading
from _thread import LockType
from collections.abc import Callable, Generator, Iterator

import anyio
from fastapi import HTTPException
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send


class _GenerationStream(Iterator[bytes]):
    def __init__(self, source: Generator[bytes, None, None]):
        self.source = source
        self._iteration_lock = threading.Lock()
        self._closed = False

    def __next__(self) -> bytes:
        with self._iteration_lock:
            if self._closed:
                raise StopIteration
            return next(self.source)

    def close(self) -> None:
        # A cancelled response must not close a generator still executing in a
        # worker thread, or admit another request before that worker stops.
        with self._iteration_lock:
            if self._closed:
                return
            self._closed = True
            self.source.close()


class GenerationStreamingResponse(StreamingResponse):
    """Admit generation before headers, with no lease on an uninvoked response."""

    def __init__(self, source: Callable[[], Generator[bytes, None, None]], lock: LockType):
        self._source = source
        self._generation_lock = lock
        self._stream: _GenerationStream | None = None
        super().__init__(
            (),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._generation_lock.acquire(blocking=False):
            raise HTTPException(409, "Một yêu cầu khác đang chạy. Máy cục bộ xử lý tuần tự.")
        try:
            self._stream = _GenerationStream(self._source())
            self.body_iterator = iterate_in_threadpool(self._stream)
            await super().__call__(scope, receive, send)
        finally:
            # Background tasks do not run on every send failure/disconnect.
            # Close even an unread source, waiting for any executing next().
            try:
                with anyio.CancelScope(shield=True):
                    if self._stream is not None:
                        await run_in_threadpool(self._stream.close)
            finally:
                self._generation_lock.release()
