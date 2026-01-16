import asyncio
import threading
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")

CancelCallback = Callable[[], None | Awaitable[None]]


class AsyncQueue(Generic[T]):
    """
    Single-consumer async iterable queue for streaming.

    Thread-safe for producers: enqueue/finish/fail can be called from any thread.
    Consumer must run in the event loop where iteration started.
    """

    def __init__(
        self,
        on_cancel: CancelCallback | None = None,
        max_size: int | None = None,
    ):
        self._queue: deque[T] = deque()
        self._on_cancel = on_cancel
        self._max_size = max_size

        self._waiter: asyncio.Future[T] | None = None
        self._done = False
        self._error: BaseException | None = None
        self._started = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None

    def _on_loop_thread(self) -> bool:
        return self._loop_thread is threading.current_thread()

    def __aiter__(self):
        if self._started:
            raise RuntimeError("Queue can only be iterated once")
        self._started = True
        self._loop = asyncio.get_running_loop()
        self._loop_thread = threading.current_thread()
        return self

    async def __anext__(self) -> T:
        if self._queue:
            return self._queue.popleft()

        if self._done:
            raise StopAsyncIteration
        if self._error:
            raise self._error

        self._waiter = asyncio.get_running_loop().create_future()
        try:
            return await self._waiter
        finally:
            self._waiter = None

    def _do_enqueue(self, value: T) -> None:
        if self._done or self._error:
            return
        if self._waiter and not self._waiter.done():
            self._waiter.set_result(value)
        else:
            self._queue.append(value)

    def enqueue(self, value: T) -> None:
        if self._done:
            raise RuntimeError("Cannot enqueue to finished queue")
        if self._error:
            raise RuntimeError("Cannot enqueue to errored queue")
        if self._max_size and len(self._queue) >= self._max_size:
            raise RuntimeError(f"Queue full (max_size={self._max_size})")

        if self._loop and not self._on_loop_thread():
            self._loop.call_soon_threadsafe(self._do_enqueue, value)
        else:
            self._do_enqueue(value)

    def _do_finish(self) -> None:
        self._done = True
        if self._waiter and not self._waiter.done():
            self._waiter.set_exception(StopAsyncIteration())

    def finish(self) -> None:
        if self._loop and not self._on_loop_thread():
            self._loop.call_soon_threadsafe(self._do_finish)
        else:
            self._do_finish()

    def _do_fail(self, error: BaseException) -> None:
        self._error = error
        self._done = True
        if self._waiter and not self._waiter.done():
            self._waiter.set_exception(error)

    def fail(self, error: BaseException) -> None:
        if self._loop and not self._on_loop_thread():
            self._loop.call_soon_threadsafe(self._do_fail, error)
        else:
            self._do_fail(error)

    async def aclose(self) -> None:
        self._done = True
        if self._waiter and not self._waiter.done():
            self._waiter.set_exception(StopAsyncIteration())
        if self._on_cancel:
            result = self._on_cancel()
            if result is not None:
                await result

    @property
    def is_finished(self) -> bool:
        return self._done

    @property
    def pending(self) -> int:
        return len(self._queue)
