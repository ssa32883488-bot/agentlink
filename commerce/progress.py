"""对话流式进度：工具内部可上报细粒度状态，供 SSE status 事件展示。"""
from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Awaitable, Callable
from typing import Any

ProgressFn = Callable[[str], Any]

_progress_cb: contextvars.ContextVar[ProgressFn | None] = contextvars.ContextVar(
    "agentlink_progress_cb", default=None
)


def set_progress(cb: ProgressFn | None):
    return _progress_cb.set(cb)


def reset_progress(token) -> None:
    _progress_cb.reset(token)


def report(text: str, *, phase: str | None = None) -> None:
    """同步上报一行进度（工具内任意处可调）。"""
    cb = _progress_cb.get()
    if not cb or not text:
        return
    try:
        result = cb(text, phase) if phase is not None else cb(text)
        if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(result)  # type: ignore[arg-type]
            except RuntimeError:
                pass
    except Exception:  # noqa: BLE001
        pass


def make_queue_reporter(queue: asyncio.Queue) -> ProgressFn:
    def _put(text: str, phase: str | None = None) -> None:
        payload: dict[str, Any] = {"type": "status", "text": text}
        if phase:
            payload["phase"] = phase
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass

    return _put


async def drain_status_queue(queue: asyncio.Queue) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while True:
        try:
            out.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return out
