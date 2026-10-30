# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from commerce_v2 import case_store, thread_store
from commerce_v2.buyer_path_group import handle_group_turn
from commerce_v2.buyer_path_normal import handle_turn
from commerce_v2.models import Phase
from commerce_v2.progress import ProgressFn, emit as prog


async def handle_chat(
    agent_id: str,
    text: str,
    *,
    thread_id: str | None = None,
    progress: ProgressFn = None,
    think_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    th = thread_store.ensure_thread(agent_id, thread_id)
    tid = th["id"]

    # 线程绑定案：无则新建
    case = None
    if th.get("case_id"):
        case = case_store.get_case(agent_id, th["case_id"])
    if not case:
        case = case_store.create_case(agent_id)
        thread_store.bind_case(agent_id, tid, case["case_id"])
    else:
        case_store.set_active(agent_id, case["case_id"])
        # 已完结案 + 新需求 → 新案并绑到本线程
        if case.get("state") in (Phase.ACTIVE.value, Phase.IDLE.value) and _looks_like_new_demand(text):
            case = case_store.create_case(agent_id)
            thread_store.bind_case(agent_id, tid, case["case_id"])

    await prog(progress, "正在接收用户消息并装载案件上下文…", "think")
    case_store.append_history(case, "user", text)

    g = await handle_group_turn(case, text, progress=progress)
    if g is not None:
        out = g
    else:
        out = await handle_turn(case, text, progress=progress)

    case = out["case"]
    await prog(progress, "正在组织回复…", "reply")
    if think_steps is not None:
        case_store.attach_think_to_last_assistant(case, think_steps)
    case_store.save_case(case)
    thread_store.bind_case(agent_id, tid, case["case_id"])

    # 同步本轮消息到线程历史（供保存/切换/查看）
    reply = out.get("reply") or ""
    thread_msgs = [
        {
            "role": "user",
            "content": text,
            "meta": {"case_id": case.get("case_id"), "thread_id": tid},
        },
        {
            "role": "assistant",
            "content": reply,
            "meta": {
                "case_id": case.get("case_id"),
                "thread_id": tid,
                "state": case.get("state"),
                "think_steps": list(think_steps or []),
                "ui_widgets": out.get("ui_widgets") or [],
                "engine": "commerce_v2",
            },
        },
    ]
    thread_store.append_messages(agent_id, tid, thread_msgs)

    return {
        "ok": True,
        "engine": "commerce_v2",
        "reply": reply,
        "message": reply,
        "case_id": case.get("case_id"),
        "case": case,
        "case_state": case.get("state"),
        "ui_widgets": out.get("ui_widgets") or [],
        "think_steps": list(think_steps or []),
        "thread_id": tid,
        "runtime": "v2",
        "group_room": case.get("group_room") or out.get("group_room"),
        "open_group_room": bool(out.get("open_group_room") or case.get("group_room")),
    }


def _looks_like_new_demand(text: str) -> bool:
    return any(k in (text or "") for k in ("采购", "买", "脚轮", "询价", "组群"))


async def stream_chat(agent_id: str, text: str, *, thread_id: str | None = None) -> AsyncIterator[dict[str, Any]]:
    q: asyncio.Queue = asyncio.Queue()
    think_steps: list[dict[str, Any]] = []

    async def progress(msg: str, phase: str = "tool") -> None:
        think_steps.append({"text": msg, "phase": phase})
        await q.put({"type": "status", "text": msg, "phase": phase, "engine": "commerce_v2"})
        await asyncio.sleep(0.12)

    async def runner() -> None:
        try:
            await progress("正在理解你的意图…", "think")
            result = await handle_chat(
                agent_id, text, thread_id=thread_id, progress=progress, think_steps=think_steps
            )
            await q.put({"type": "_result", "result": result})
        except Exception as exc:  # noqa: BLE001
            await q.put({"type": "error", "message": str(exc)})
        finally:
            await q.put(None)

    task = asyncio.create_task(runner())
    result: dict[str, Any] | None = None
    try:
        while True:
            ev = await q.get()
            if ev is None:
                break
            if ev.get("type") == "_result":
                result = ev["result"]
                continue
            yield ev

        if result is None:
            yield {"type": "error", "message": "无结果"}
            return

        if result.get("ui_widgets"):
            yield {
                "type": "meta",
                "case_id": result.get("case_id"),
                "thread_id": result.get("thread_id"),
                "ui_widgets": result.get("ui_widgets"),
                "case": result.get("case"),
                "think_steps": think_steps,
            }

        reply = result.get("reply") or ""
        chunk = 48
        for i in range(0, len(reply), chunk):
            yield {"type": "token", "text": reply[i : i + chunk]}
            await asyncio.sleep(0.02)

        case = result.get("case") or {}
        done = {
            "type": "done",
            "reply": reply,
            "message": reply,
            "case_id": result.get("case_id"),
            "thread_id": result.get("thread_id"),
            "case_state": result.get("case_state") or case.get("state"),
            "ui_widgets": result.get("ui_widgets") or [],
            "think_steps": think_steps,
            "case": case,
            "engine": "commerce_v2",
            "data": result.get("data"),
            "group_room": case.get("group_room") or result.get("group_room"),
            "open_group_room": bool(result.get("open_group_room") or case.get("group_room")),
        }
        yield done
        yield {**done, "type": "final"}
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except Exception:  # noqa: BLE001
                pass
