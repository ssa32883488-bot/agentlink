# -*- coding: utf-8 -*-
"""v2 FastAPI 挂载：对话 / 案件 / Gate / 工单。"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from commerce_v2 import case_store, order_ids, order_sync, thread_store
from commerce_v2.gates import ack_logistics_gate, ack_order_gate
from commerce_v2.runtime_flag import use_v2


class ChatIn(BaseModel):
    text: str
    thread_id: str | None = None


class ThreadCreateIn(BaseModel):
    title: str | None = None


class AckIn(BaseModel):
    ticket_id: str = Field(..., description="order_id or logistics_id")


class OrderSyncIn(BaseModel):
    order: dict[str, Any]
    place_order: str | None = None


class LogisticsSyncIn(BaseModel):
    logistics: dict[str, Any]


def mount_v2(app: FastAPI, *, agent_id: str, aic: str = "") -> None:
    # 延迟导入：避免供应/物流仅 import use_v2 时拖入采购 LLM 链
    from commerce_v2.chat_api import handle_chat, stream_chat

    router = APIRouter(tags=["commerce_v2"])

    @router.get("/api/erp/chat-engine")
    def chat_engine() -> dict[str, Any]:
        return {"engine": "commerce_v2", "llm": False, "stream": True, "runtime": "v2"}

    @router.post("/api/erp/chat")
    async def erp_chat(body: ChatIn) -> dict[str, Any]:
        return await handle_chat(agent_id, body.text, thread_id=body.thread_id)

    @router.post("/api/erp/chat/stream")
    async def erp_chat_stream(body: ChatIn) -> StreamingResponse:
        async def event_source() -> AsyncIterator[bytes]:
            try:
                async for ev in stream_chat(agent_id, body.text, thread_id=body.thread_id):
                    yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n".encode("utf-8")
            except Exception as exc:  # noqa: BLE001
                err = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
                yield f"data: {err}\n\n".encode("utf-8")
            yield b"data: {\"type\":\"close\"}\n\n"

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/erp/chat/threads")
    def threads() -> dict[str, Any]:
        items = thread_store.list_threads(agent_id)
        active = thread_store.active_thread_id(agent_id)
        return {"items": items, "active_thread_id": active}

    @router.post("/api/erp/chat/threads")
    def thread_new(body: ThreadCreateIn | None = None) -> dict[str, Any]:
        case = case_store.create_case(agent_id)
        t = thread_store.create_thread(
            agent_id,
            title=(body.title if body else None),
            case_id=case.get("case_id"),
        )
        return t

    @router.post("/api/erp/chat/threads/{thread_id}/activate")
    def thread_act(thread_id: str) -> dict[str, Any]:
        try:
            out = thread_store.activate(agent_id, thread_id)
        except KeyError:
            raise HTTPException(404, "对话不存在") from None
        cid = out.get("case_id")
        if cid:
            case_store.set_active(agent_id, cid)
        return out

    @router.delete("/api/erp/chat/threads/{thread_id}")
    def thread_del(thread_id: str) -> dict[str, Any]:
        try:
            return thread_store.delete_thread(agent_id, thread_id)
        except KeyError:
            raise HTTPException(404, "对话不存在") from None

    @router.get("/api/flow/cases")
    def flow_cases() -> dict[str, Any]:
        return {"items": case_store.list_cases(agent_id)}

    @router.get("/api/flow/cases/{case_id}")
    def flow_case(case_id: str) -> dict[str, Any]:
        c = case_store.get_case(agent_id, case_id)
        if not c:
            raise HTTPException(404, "case not found")
        # 打开对话时对账：订单已生效但案仍停在等待对端 → 补询物流提醒
        try:
            oid = c.get("order_id")
            if oid and not c.get("logistics_id"):
                o = order_ids.get_order(oid)
                if o and o.get("effective") and c.get("state") in (
                    "ORDER_PEER_PENDING",
                    "ORDER_DRAFT",
                    "ORDER_EFFECTIVE",
                ):
                    from commerce_v2.order_sync import _promote_buyer_case_for_order

                    _promote_buyer_case_for_order(o)
                    c = case_store.get_case(agent_id, case_id) or c
        except Exception:
            pass
        return c

    @router.get("/api/erp/conversations")
    def conversations(thread_id: str | None = None, limit: int = 80) -> dict[str, Any]:
        """按线程返回历史消息（含 think_steps）。"""
        tid = thread_id or thread_store.active_thread_id(agent_id)
        if not tid:
            th = thread_store.ensure_thread(agent_id)
            tid = th["id"]
        tid, msgs = thread_store.list_messages(agent_id, tid, limit=limit)
        case = None
        th = thread_store.get_thread(agent_id, tid) if tid else None
        if th and th.get("case_id"):
            case = case_store.get_case(agent_id, th["case_id"])
        if not case:
            case = case_store.get_case(agent_id)
        items: list[dict[str, Any]] = []
        for h in msgs:
            base_meta = {
                "case_id": (case or {}).get("case_id") or (th or {}).get("case_id"),
                "state": (case or {}).get("state"),
                "engine": "commerce_v2",
                "thread_id": tid,
            }
            hm = h.get("meta") if isinstance(h.get("meta"), dict) else {}
            items.append(
                {
                    "role": h.get("role") or "assistant",
                    "content": h.get("content") or h.get("text") or "",
                    "meta": {**base_meta, **hm},
                }
            )
        # 打开历史时对账：货单已生效且未建物流 → 补询物流 AskUser
        if case and case.get("order_id") and not case.get("logistics_id"):
            try:
                o = order_ids.get_order(case["order_id"])
                if o and o.get("effective") and case.get("state") in (
                    "ORDER_PEER_PENDING",
                    "ORDER_DRAFT",
                    "ORDER_EFFECTIVE",
                ):
                    from commerce_v2.order_sync import _promote_buyer_case_for_order

                    _promote_buyer_case_for_order(o)
                    case = case_store.get_case(agent_id, case.get("case_id")) or case
            except Exception:
                pass
        # 当前案未决断点控件挂到末条助手（仅当该线程绑定当前案）
        if (
            case
            and th
            and th.get("case_id") == case.get("case_id")
            and items
            and items[-1].get("role") != "user"
        ):
            try:
                if case.get("pending_choices"):
                    items[-1].setdefault("meta", {}).setdefault("ui_widgets", []).append(
                        case["pending_choices"]
                    )
                # hitl_pending 可能显式为 null，不能用 get 默认值
                hitl = case.get("hitl_pending") or {}
                if hitl.get("gate") == "confirm_shortlist" and case.get("candidates"):
                    from commerce_v2.widgets import shortlist_widget

                    items[-1].setdefault("meta", {}).setdefault("ui_widgets", []).append(
                        shortlist_widget(case)
                    )
            except Exception:
                pass
        return {
            "items": items,
            "thread_id": tid,
            "case_id": (case or {}).get("case_id") or (th or {}).get("case_id"),
        }

    @router.get("/api/erp/shared-facts")
    def shared_facts() -> dict[str, Any]:
        return {"items": []}

    @router.get("/api/erp/tickets")
    def tickets(status: str | None = None, include_archived: bool = True, limit: int = 50) -> dict[str, Any]:
        items = order_ids.list_open_tickets(agent_id)[:limit]
        if status == "open":
            items = [t for t in items if t.get("status") == "open"]
        return {"items": items}

    @router.post("/api/v2/gate/ack-order")
    def gate_ack_order(body: AckIn) -> dict[str, Any]:
        try:
            return ack_order_gate(agent_id, body.ticket_id)
        except KeyError:
            raise HTTPException(404, "order not found") from None

    @router.post("/api/v2/gate/ack-logistics")
    def gate_ack_logistics(body: AckIn) -> dict[str, Any]:
        try:
            return ack_logistics_gate(agent_id, body.ticket_id)
        except KeyError:
            raise HTTPException(404, "logistics not found") from None

    @router.post("/api/erp/tickets/{ticket_id}/ack-order")
    def ticket_ack_order(ticket_id: str) -> dict[str, Any]:
        try:
            return ack_order_gate(agent_id, ticket_id)
        except KeyError:
            raise HTTPException(404, "order not found") from None

    @router.post("/api/erp/tickets/{ticket_id}/ack-logistics")
    def ticket_ack_logistics(ticket_id: str) -> dict[str, Any]:
        try:
            return ack_logistics_gate(agent_id, ticket_id)
        except KeyError:
            raise HTTPException(404, "logistics not found") from None

    @router.post("/api/erp/v2/orders/sync")
    def sync_order(body: OrderSyncIn) -> dict[str, Any]:
        order = dict(body.order or {})
        if body.place_order is not None and "place_order" not in order:
            order["place_order"] = body.place_order
        try:
            # 采购云接收供应确认回写：已有单合并，不强制 place_order=on
            o = order_sync.apply_order(order, require_place_on_for_create=False)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True, "order_id": o.get("order_id")}

    @router.post("/api/erp/v2/logistics/sync")
    def sync_logistics(body: LogisticsSyncIn) -> dict[str, Any]:
        try:
            row = order_sync.apply_logistics(body.logistics)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True, "logistics_id": row.get("logistics_id")}

    @router.get("/api/v2/health")
    def v2_health() -> dict[str, Any]:
        return {"ok": True, "agent_id": agent_id, "aic": aic, "runtime": "v2"}

    app.include_router(router)
