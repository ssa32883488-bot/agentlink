from __future__ import annotations

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from commerce import supplier_service as ss
from commerce.env_loader import llm_enabled
from commerce.seed import seed_all


class ChatIn(BaseModel):
    text: str
    thread_id: str | None = None


class ThreadCreateIn(BaseModel):
    title: str | None = None


def mount_supplier_commerce(app, *, agent_id: str) -> None:
    # 确保种子存在
    try:
        seed_all(reset=False)
    except Exception:
        seed_all(reset=True)

    from commerce import chat_sessions as cs
    from commerce import chat_supplier as csup
    from commerce import chat_supplier_wit as csw
    from commerce.office_routes import mount_office

    csup.configure(agent_id=agent_id)
    csw.configure(agent_id=agent_id)
    mount_office(app, agent_id=agent_id)

    router = APIRouter(tags=[f"commerce-{agent_id}"])

    @router.get("/api/erp/merchant")
    def merchant() -> dict[str, Any]:
        from commerce.merchant import profile

        return profile(agent_id)

    @router.get("/api/erp/catalog")
    def catalog() -> dict[str, Any]:
        return {"items": ss.list_catalog(agent_id)}

    @router.get("/api/erp/promotions")
    def promotions() -> dict[str, Any]:
        """本厂已公示优惠政策（policy.yaml promotions）。"""
        from commerce.chat_supplier_wit import _promotions_payload, configure as wit_configure

        wit_configure(agent_id=agent_id)
        return _promotions_payload()

    @router.get("/api/erp/rfq-inbox")
    def inbox() -> dict[str, Any]:
        return {"items": ss.list_rfq_inbox(agent_id)}

    @router.get("/api/erp/chat/threads")
    def chat_threads() -> dict[str, Any]:
        items = cs.list_threads(agent_id)
        active = cs.active_thread_id(agent_id) or (items[0]["id"] if items else None)
        return {"items": items, "active_thread_id": active}

    @router.post("/api/erp/chat/threads")
    def chat_thread_new(body: ThreadCreateIn | None = None) -> dict[str, Any]:
        return cs.create_thread(agent_id, title=(body.title if body else None))

    @router.post("/api/erp/chat/threads/{thread_id}/activate")
    def chat_thread_activate(thread_id: str) -> dict[str, Any]:
        if not cs.get_thread(agent_id, thread_id):
            raise HTTPException(404, "对话不存在")
        cs.set_active_thread(agent_id, thread_id)
        return {"ok": True, "thread_id": thread_id}

    @router.delete("/api/erp/chat/threads/{thread_id}")
    def chat_thread_delete(thread_id: str) -> dict[str, Any]:
        if not cs.get_thread(agent_id, thread_id):
            raise HTTPException(404, "对话不存在")
        was_active = cs.active_thread_id(agent_id) == thread_id
        cs.delete_thread(agent_id, thread_id)
        nxt = None
        if was_active:
            items = cs.list_threads(agent_id)
            if items:
                nxt = items[0]["id"]
                cs.set_active_thread(agent_id, nxt)
            else:
                nxt = cs.create_thread(agent_id, title="新对话")["id"]
        return {"ok": True, "deleted": thread_id, "active_thread_id": nxt or cs.active_thread_id(agent_id)}

    @router.get("/api/erp/conversations")
    def erp_conv(thread_id: str | None = None) -> dict[str, Any]:
        tid = thread_id or cs.active_thread_id(agent_id)
        if tid:
            cs.set_active_thread(agent_id, tid)
        return {"items": csup.list_conversations(agent_id, thread_id=tid), "thread_id": tid}

    @router.post("/api/erp/chat")
    async def erp_chat(body: ChatIn) -> dict[str, Any]:
        # 与采购一致：一律 Wit + DeepSeek；禁止固定话术/规则直答回落
        if not llm_enabled():
            raise HTTPException(
                503,
                "未启用 LLM：请配置 LLM_API_KEY 且 SUPPLIER_CHAT_ENGINE/BUYER_CHAT_ENGINE=wit",
            )
        return await csw.handle_supplier_chat_wit(body.text, thread_id=body.thread_id)

    @router.post("/api/erp/chat/stream")
    async def erp_chat_stream(body: ChatIn) -> StreamingResponse:
        async def event_source() -> AsyncIterator[bytes]:
            if not llm_enabled():
                err = json.dumps(
                    {
                        "type": "error",
                        "message": "未启用 LLM：请配置 LLM_API_KEY 且 SUPPLIER_CHAT_ENGINE/BUYER_CHAT_ENGINE=wit",
                        "engine": "wit",
                    },
                    ensure_ascii=False,
                )
                yield f"data: {err}\n\n".encode("utf-8")
                yield b'data: {"type":"close"}\n\n'
                return
            try:
                async for ev in csw.stream_supplier_chat_wit(body.text, thread_id=body.thread_id):
                    payload = json.dumps(ev, ensure_ascii=False, default=str)
                    yield f"data: {payload}\n\n".encode("utf-8")
            except Exception as exc:  # noqa: BLE001
                err = json.dumps({"type": "error", "message": f"对话失败：{exc}"}, ensure_ascii=False)
                yield f"data: {err}\n\n".encode("utf-8")
            yield b'data: {"type":"close"}\n\n'

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/erp/chat-engine")
    def erp_chat_engine() -> dict[str, Any]:
        return {
            "engine": "wit" if llm_enabled() else "disabled",
            "llm": llm_enabled(),
            "stream": True,
            "faq_direct": False,
            "agent_id": agent_id,
        }

    @router.get("/api/erp/workbench-summary")
    def workbench_summary() -> dict[str, Any]:
        from commerce import tickets as tk

        notes = []
        try:
            from commerce import notify

            notes = notify.list_notifications(agent_id, unread_only=True, limit=20)
        except Exception:
            pass
        tickets = tk.list_tickets(agent_id, include_archived=False, limit=20)
        return {
            "unread_notifications": len(notes),
            "open_tickets": len([t for t in tickets if t.get("status") in ("open", "suspended")]),
            "order_pending": len(
                [
                    t
                    for t in tickets
                    if t.get("kind") == "order"
                    and t.get("status") == "open"
                    and not (t.get("state") or {}).get("supplier_order_ack")
                ]
            ),
            "logistics_pending": len(
                [
                    t
                    for t in tickets
                    if t.get("kind") == "logistics_order"
                    and t.get("status") == "open"
                    and not (t.get("state") or {}).get("supplier_logistics_ack")
                ]
            ),
            "catalog_count": len(ss.list_catalog(agent_id)),
            "inbox_count": len(ss.list_rfq_inbox(agent_id)),
        }

    app.include_router(router)
