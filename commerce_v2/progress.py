# -*- coding: utf-8 -*-
"""对话过程动作上报：供 SSE status 事件驱动 UI 思考轨迹。"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

ProgressFn = Optional[Callable[[str, str], Awaitable[None]]]


async def emit(progress: ProgressFn, text: str, phase: str = "tool") -> None:
    if not progress or not text:
        return
    await progress(text, phase)
    # 让出事件循环，便于 SSE 立刻刷到浏览器
    await asyncio.sleep(0.12)


def bind_queue(q: asyncio.Queue) -> ProgressFn:
    async def _progress(text: str, phase: str = "tool") -> None:
        await q.put({"type": "status", "text": text, "phase": phase, "engine": "commerce_v2"})

    return _progress
