"""挂到采购商A FastAPI 上的商城/ERP API。"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from commerce import buyer_service as bs
from commerce.chat_buyer_wit import handle_buyer_chat_wit, stream_buyer_chat_wit
from commerce.env_loader import llm_enabled
from commerce.rfq_bridge import rfq_shortages

router = APIRouter(tags=["commerce-buyer"])

class MallOrderIn(BaseModel):
    sku: str = Field(..., description="CHAIR-A 或 CHAIR-B")
    qty: int = Field(..., ge=1, le=500)
    customer_name: str = "C端用户"


class ChatIn(BaseModel):
    text: str
    thread_id: str | None = None


class ThreadCreateIn(BaseModel):
    title: str | None = None


class ReplenishIn(BaseModel):
    notification_id: str | None = None


def _mount_buyer_mall_only(app, *, agent_id: str) -> None:
    """v2 模式下保留商城/库存只读 API，不注册 wit 对话。"""
    r = APIRouter(tags=["commerce-buyer-mall-v2"])

    @r.get("/api/mall/products")
    def mall_products() -> dict[str, Any]:
        return {"items": bs.list_products()}

    @r.post("/api/mall/orders")
    def mall_order(body: MallOrderIn) -> dict[str, Any]:
        try:
            return bs.place_sales_order(sku=body.sku, qty=body.qty, customer_name=body.customer_name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @r.get("/api/erp/merchant")
    def erp_merchant() -> dict[str, Any]:
        from commerce.merchant import profile

        return profile(agent_id)

    @r.get("/api/erp/inventory")
    def erp_inventory() -> dict[str, Any]:
        return {"items": bs.list_inventory()}

    @r.get("/api/erp/sales-orders")
    def erp_sales() -> dict[str, Any]:
        return {"items": bs.list_sales_orders()}

    @r.get("/api/erp/notifications")
    def erp_notes(unread_only: bool = False) -> dict[str, Any]:
        return {"items": bs.list_notifications(unread_only=unread_only)}

    app.include_router(r)


def mount_buyer_commerce(app, *, aic: str, agent_id: str = "buyer-a") -> None:
    bs.configure(agent_id)
    from commerce_v2.routes import mount_v2, use_v2

    # 默认 AGENTLINK_RUNTIME=v2：切断旧 wit/组群路由，改挂 commerce_v2
    if use_v2():
        mount_v2(app, agent_id=agent_id, aic=aic)
        from commerce.office_routes import mount_office

        # 邮箱等办公路由仍挂；tickets/chat 已由 v2 先注册占位
        mount_office(app, agent_id=agent_id)
        _mount_buyer_mall_only(app, agent_id=agent_id)
        return

    from commerce import chat_sessions as cs
    from commerce.chat_buyer_wit import configure as configure_wit
    from commerce.group_routes import mount_group_routes
    from commerce.office_routes import mount_office

    configure_wit(agent_id=agent_id)
    mount_office(app, agent_id=agent_id)
    mount_group_routes(app, aic=aic, agent_id=agent_id)

    @router.get("/api/erp/chat/threads")
    def chat_threads() -> dict[str, Any]:
        items = cs.list_threads(agent_id)
        active = cs.active_thread_id(agent_id) or (items[0]["id"] if items else None)
        return {"items": items, "active_thread_id": active}

    @router.post("/api/erp/chat/threads")
    def chat_thread_new(body: ThreadCreateIn | None = None) -> dict[str, Any]:
        from commerce.chat_buyer_wit import _restore_case_for_thread, _set_active_case, _set_active_thread

        t = cs.create_thread(agent_id, title=(body.title if body else None))
        _set_active_thread(t.get("id"))
        _set_active_case(None)  # 新窗不继承上一窗采购案上下文
        _restore_case_for_thread(t.get("id"))
        return t

    @router.post("/api/erp/chat/threads/{thread_id}/activate")
    def chat_thread_activate(thread_id: str) -> dict[str, Any]:
        from commerce.chat_buyer_wit import _restore_case_for_thread, _set_active_thread

        if not cs.get_thread(agent_id, thread_id):
            raise HTTPException(404, "对话不存在")
        cs.set_active_thread(agent_id, thread_id)
        _set_active_thread(thread_id)
        cid = _restore_case_for_thread(thread_id)
        meta = cs.get_thread_meta(agent_id, thread_id)
        return {
            "ok": True,
            "thread_id": thread_id,
            "case_id": cid,
            "subject_product": meta.get("subject_product"),
        }

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

    @router.get("/api/erp/shared-facts")
    def shared_facts() -> dict[str, Any]:
        return {"items": cs.list_shared_facts(agent_id)}

    @router.get("/api/mall/products")
    def mall_products() -> dict[str, Any]:
        return {"items": bs.list_products()}

    @router.post("/api/mall/orders")
    def mall_order(body: MallOrderIn) -> dict[str, Any]:
        try:
            return bs.place_sales_order(sku=body.sku, qty=body.qty, customer_name=body.customer_name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.get("/api/erp/merchant")
    def erp_merchant() -> dict[str, Any]:
        from commerce.merchant import profile

        return profile(agent_id)

    @router.get("/api/erp/inventory")
    def erp_inventory() -> dict[str, Any]:
        return {"items": bs.list_inventory()}

    @router.get("/api/erp/sales-orders")
    def erp_sales() -> dict[str, Any]:
        return {"items": bs.list_sales_orders()}

    @router.get("/api/erp/notifications")
    def erp_notes(unread_only: bool = False) -> dict[str, Any]:
        return {"items": bs.list_notifications(unread_only=unread_only)}

    @router.post("/api/erp/notifications/{nid}/read")
    def erp_note_read(nid: str) -> dict[str, str]:
        bs.mark_notification_read(nid)
        return {"status": "ok"}

    @router.get("/api/erp/conversations")
    def erp_conv(thread_id: str | None = None) -> dict[str, Any]:
        tid = thread_id or cs.active_thread_id(agent_id)
        if tid:
            cs.set_active_thread(agent_id, tid)
        return {"items": bs.list_conversations(thread_id=tid), "thread_id": tid}

    @router.get("/api/erp/audit-tasks")
    def erp_tasks() -> dict[str, Any]:
        return {"items": bs.list_audit_tasks()}

    async def _rfq_runner(shortages: list[dict[str, Any]]) -> dict[str, Any]:
        return await rfq_shortages(shortages, leader_aic=aic, local_agent_id=agent_id)

    @router.post("/api/erp/chat")
    async def erp_chat(body: ChatIn) -> dict[str, Any]:
        # 一律走 DeepSeek/Wit；不再回落到 FAQ/规则直答
        if not llm_enabled():
            raise HTTPException(
                503,
                "未启用 LLM：请配置 LLM_API_KEY 且 BUYER_CHAT_ENGINE=wit",
            )
        return await handle_buyer_chat_wit(body.text, run_rfq=_rfq_runner, thread_id=body.thread_id)

    @router.post("/api/erp/chat/stream")
    async def erp_chat_stream(body: ChatIn) -> StreamingResponse:
        async def event_source() -> AsyncIterator[bytes]:
            if not llm_enabled():
                err = json.dumps(
                    {
                        "type": "error",
                        "message": "未启用 LLM：请配置 LLM_API_KEY 且 BUYER_CHAT_ENGINE=wit",
                        "engine": "wit",
                    },
                    ensure_ascii=False,
                )
                yield f"data: {err}\n\n".encode("utf-8")
                yield b"data: {\"type\":\"close\"}\n\n"
                return
            try:
                async for ev in stream_buyer_chat_wit(
                    body.text, run_rfq=_rfq_runner, thread_id=body.thread_id
                ):
                    payload = json.dumps(ev, ensure_ascii=False, default=str)
                    yield f"data: {payload}\n\n".encode("utf-8")
            except Exception as exc:  # noqa: BLE001
                err = json.dumps(
                    {"type": "error", "message": f"流式输出失败：{exc}"},
                    ensure_ascii=False,
                )
                yield f"data: {err}\n\n".encode("utf-8")
            yield b"data: {\"type\":\"close\"}\n\n"

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/api/erp/chat-engine")
    def erp_chat_engine() -> dict[str, Any]:
        return {
            "engine": "wit" if llm_enabled() else "disabled",
            "llm": llm_enabled(),
            "stream": True,
            "faq_direct": False,
        }

    @router.post("/api/erp/replenish")
    async def erp_replenish(body: ReplenishIn | None = None) -> dict[str, Any]:
        payload = bs.latest_shortage_payload()
        if not payload:
            inv = bs.list_inventory()
            shortages = [
                {
                    "material_code": i["code"],
                    "name": i["name"],
                    "unit": i["unit"],
                    "short_vs_safety": round(float(i["safety_stock"]) - float(i["available"]), 2),
                    "preferred_supplier": i["preferred_supplier"],
                    "need": max(float(i["safety_stock"]) - float(i["available"]), 1),
                }
                for i in inv
                if i.get("low")
            ]
        else:
            shortages = payload.get("shortages") or []
        if not shortages:
            raise HTTPException(400, "当前没有可补货缺口")
        result = await rfq_shortages(shortages, leader_aic=aic, local_agent_id=agent_id)
        bs.append_conversation(
            "assistant",
            f"已从通知发起补货询价，收到报价 {result.get('quote_count')} 份。",
            {"intent": "replenish_button", "result": result},
        )
        if body and body.notification_id:
            bs.mark_notification_read(body.notification_id)
        return result

    @router.post("/api/erp/shipping-quote/accept")
    def accept_shipping_quote(body: dict[str, Any]) -> dict[str, Any]:
        """供应↔物流双边确认后回传运费报价给采购方。"""
        from commerce import notify
        from commerce import procurement_case as pc

        case_id = body.get("case_id")
        quote = body.get("shipping_quote") or {}
        if case_id:
            try:
                case = pc.get_case(str(case_id))
                if case:
                    pc.update_case(
                        str(case_id),
                        shipping_quote={
                            "payload": quote,
                            "logistics_ticket_id": body.get("logistics_ticket_id"),
                            "order_ticket_id": body.get("order_ticket_id"),
                            "supplier_agent_id": body.get("supplier_agent_id"),
                            "effective": True,
                        },
                    )
            except Exception:
                pass
        notify.push(
            agent_id,
            title="物流报价已生效",
            body=(
                f"案 {case_id or '—'} 运费 {quote.get('shipping_cost', '—')} "
                f"· ETA {quote.get('eta_days', '—')}天 · 来自供应/物流双边确认"
            ),
            level="info",
            payload={
                "case_id": case_id,
                "kind": "shipping_quote_effective",
                "shipping_quote": quote,
                "logistics_ticket_id": body.get("logistics_ticket_id"),
            },
        )
        return {"ok": True, "case_id": case_id, "shipping_quote": quote}

    app.include_router(router)
