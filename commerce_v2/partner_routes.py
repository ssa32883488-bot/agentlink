# -*- coding: utf-8 -*-
"""供应 / 物流侧 v2 挂载：Partner 智力对话 + 工单 Gate。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from commerce_v2 import order_ids, order_sync, thread_store
from commerce_v2.catalog import LOGISTICS_REQUIRED, SUPPLIERS
from commerce_v2.gates import ack_logistics_gate, ack_order_gate
from commerce_v2 import partner_logistics as plog
from commerce_v2 import partner_supplier as psup


class ChatIn(BaseModel):
    text: str
    thread_id: str | None = None


class ThreadCreateIn(BaseModel):
    title: str | None = None


class OrderSyncIn(BaseModel):
    order: dict[str, Any]
    place_order: str | None = None


class LogisticsSyncIn(BaseModel):
    logistics: dict[str, Any]


def mount_partner_v2(app: FastAPI, *, agent_id: str) -> None:
    router = APIRouter(tags=[f"commerce_v2_partner_{agent_id}"])

    @router.get("/api/erp/chat-engine")
    def chat_engine() -> dict[str, Any]:
        return {"engine": "commerce_v2_partner", "llm": False, "stream": False, "runtime": "v2"}

    @router.get("/api/v2/tools")
    def partner_tools() -> dict[str, Any]:
        """供应商工具目录；place_order 仅在采购携带 place_order=on 时落单。"""
        if agent_id.startswith("supplier"):
            return {"agent_id": agent_id, "tools": psup.list_tools()}
        return {"agent_id": agent_id, "tools": []}

    @router.get("/api/erp/merchant")
    def merchant() -> dict[str, Any]:
        from commerce.merchant import profile

        return profile(agent_id)

    @router.get("/api/erp/catalog")
    def catalog() -> dict[str, Any]:
        if agent_id in SUPPLIERS:
            skus = SUPPLIERS[agent_id]["skus"]
            return {
                "items": [
                    {
                        "sku": k,
                        "code": k,
                        "name": v["name"],
                        "list_price": v["list_price"],
                        "spec": v["spec"],
                        "promo": v.get("promo"),
                        "on_hand": 9999,
                        "strategy_tag": (v.get("promo") or {}).get("reason") or "挂牌",
                        "moq": (v.get("spec") or {}).get("moq") or 1,
                    }
                    for k, v in skus.items()
                ]
            }
        return {"items": [], "logistics_required": LOGISTICS_REQUIRED}

    @router.get("/api/erp/promotions")
    def promotions() -> dict[str, Any]:
        if agent_id not in SUPPLIERS:
            return {"items": []}
        items = []
        for sku, v in SUPPLIERS[agent_id]["skus"].items():
            if v.get("promo"):
                items.append({"sku": sku, "name": v["name"], "promo": v["promo"]})
        return {"items": items}

    # —— UI 启动所需兼容桩（避免 404 阻断整页）——
    @router.get("/api/erp/notifications")
    def notifications(unread_only: bool = False, limit: int = 20) -> dict[str, Any]:
        return {"items": []}

    @router.get("/api/erp/mailbox")
    def mailbox(folder: str | None = None) -> dict[str, Any]:
        from commerce.merchant import profile

        m = profile(agent_id)
        return {"agent_id": agent_id, "email": m.get("email") or f"{agent_id}@agentlink.local", "items": []}

    @router.get("/api/erp/rfq-inbox")
    def rfq_inbox() -> dict[str, Any]:
        return {"items": []}

    @router.get("/api/erp/inventory")
    def inventory() -> dict[str, Any]:
        if agent_id not in SUPPLIERS:
            return {"items": []}
        items = []
        for sku, v in SUPPLIERS[agent_id]["skus"].items():
            items.append(
                {
                    "code": sku,
                    "sku": sku,
                    "name": v["name"],
                    "on_hand": v.get("on_hand", 0),
                    "available": v.get("on_hand", 0),
                    "unit": (v.get("spec") or {}).get("unit") or "件",
                    "list_price": v.get("list_price"),
                }
            )
        return {"items": items}

    @router.get("/api/erp/sales-orders")
    def sales_orders() -> dict[str, Any]:
        return {"items": []}

    @router.get("/api/erp/audit-tasks")
    def audit_tasks() -> dict[str, Any]:
        return {"items": []}

    @router.get("/api/erp/office-audit")
    def office_audit() -> dict[str, Any]:
        return {"items": []}

    @router.get("/api/erp/order-provenance/list")
    def order_provenance_list() -> dict[str, Any]:
        return {"items": []}

    @router.get("/api/erp/workbench-summary")
    def workbench_summary() -> dict[str, Any]:
        tickets = order_ids.list_open_tickets(agent_id)
        open_orders = [t for t in tickets if t.get("kind") == "order" and t.get("status") == "open"]
        open_log = [t for t in tickets if t.get("kind") == "logistics_order" and t.get("status") == "open"]
        cat = 0
        if agent_id in SUPPLIERS:
            cat = len(SUPPLIERS[agent_id]["skus"])
        return {
            "unread_notifications": 0,
            "order_pending": len(open_orders),
            "logistics_pending": len(open_log),
            "catalog_count": cat,
            "inbox_count": 0,
        }

    @router.get("/api/erp/chat/threads")
    def threads() -> dict[str, Any]:
        items = thread_store.list_threads(agent_id)
        return {"items": items, "active_thread_id": thread_store.active_thread_id(agent_id)}

    @router.post("/api/erp/chat/threads")
    def thread_new(body: ThreadCreateIn | None = None) -> dict[str, Any]:
        return thread_store.create_thread(agent_id, title=(body.title if body else None))

    @router.post("/api/erp/chat/threads/{thread_id}/activate")
    def thread_act(thread_id: str) -> dict[str, Any]:
        try:
            return thread_store.activate(agent_id, thread_id)
        except KeyError:
            raise HTTPException(404, "对话不存在") from None

    @router.delete("/api/erp/chat/threads/{thread_id}")
    def thread_del(thread_id: str) -> dict[str, Any]:
        try:
            return thread_store.delete_thread(agent_id, thread_id)
        except KeyError:
            raise HTTPException(404, "对话不存在") from None

    @router.post("/api/erp/chat")
    async def erp_chat(body: ChatIn) -> dict[str, Any]:
        th = thread_store.ensure_thread(agent_id, body.thread_id)
        reply = _partner_reply(agent_id, body.text or "")
        thread_store.append_messages(
            agent_id,
            th["id"],
            [
                {"role": "user", "content": body.text or "", "meta": {"thread_id": th["id"]}},
                {
                    "role": "assistant",
                    "content": reply,
                    "meta": {"thread_id": th["id"], "engine": "commerce_v2_partner"},
                },
            ],
        )
        return {
            "ok": True,
            "engine": "commerce_v2_partner",
            "reply": reply,
            "message": reply,
            "thread_id": th["id"],
            "runtime": "v2",
        }

    @router.get("/api/erp/conversations")
    def conversations(thread_id: str | None = None, limit: int = 80) -> dict[str, Any]:
        tid, msgs = thread_store.list_messages(agent_id, thread_id, limit=limit)
        items = [
            {
                "role": m.get("role") or "assistant",
                "content": m.get("content") or m.get("text") or "",
                "meta": m.get("meta") or {},
            }
            for m in msgs
        ]
        return {"items": items, "thread_id": tid}

    @router.get("/api/erp/shared-facts")
    def shared_facts() -> dict[str, Any]:
        return {"items": []}

    @router.get("/api/erp/tickets")
    def tickets(status: str | None = None, include_archived: bool = True, limit: int = 50) -> dict[str, Any]:
        items = order_ids.list_open_tickets(agent_id)[:limit]
        if status == "open":
            items = [t for t in items if t.get("status") == "open"]
        return {"items": items}

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
            # 供应侧新建工单必须 place_order=on（用户明确下单）
            o = order_sync.apply_order(
                order,
                require_place_on_for_create=bool(agent_id.startswith("supplier")),
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True, "order_id": o.get("order_id"), "place_order": order.get("place_order")}

    @router.post("/api/erp/v2/logistics/sync")
    def sync_logistics(body: LogisticsSyncIn) -> dict[str, Any]:
        try:
            row = order_sync.apply_logistics(body.logistics)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True, "logistics_id": row.get("logistics_id")}

    @router.get("/api/v2/health")
    def v2_health() -> dict[str, Any]:
        return {"ok": True, "agent_id": agent_id, "runtime": "v2", "role": "partner"}

    app.include_router(router)


def _partner_reply(agent_id: str, text: str) -> str:
    t = text.strip()
    if agent_id == "logistics":
        if any(k in t for k in ("清单", "必填", "字段", "schema")):
            lines = [f"- {f['label']}（{f['key']}）" for f in LOGISTICS_REQUIRED]
            return "物流必填字段：\n" + "\n".join(lines)
        if "确认" in t:
            open_t = [x for x in order_ids.list_open_tickets("logistics") if x.get("status") == "open"]
            if not open_t:
                return "当前无待确认物流工单。请到工单页确认。"
            return f"有 {len(open_t)} 张待确认物流工单，请到工单页点「确认」。"
        env = plog.handle_envelope("logistics", {"schema_type": "v2.logistics_schema"})
        return f"物流 Partner 就绪。{env.get('message')} 也可直接说「必填清单」。"

    meta = SUPPLIERS.get(agent_id)
    if not meta:
        return f"未知 Partner {agent_id}"
    if any(k in t for k in ("优惠", "促销", "折扣", "满减")):
        lines = []
        for sku, v in meta["skus"].items():
            p = v.get("promo") or {}
            if p and p.get("type") not in (None, "none"):
                lines.append(f"- {sku} {v['name']}: {p.get('reason') or p}")
            else:
                lines.append(f"- {sku} {v['name']}: 无优惠政策，返回挂牌价")
        return "本厂公示优惠：\n" + "\n".join(lines)
    if "报价" in t or "询价" in t or "初报" in t:
        sku = next(iter(meta["skus"]))
        for k in meta["skus"]:
            if k in t:
                sku = k
                break
        qty = 300
        out = psup.handle_envelope(agent_id, {"schema_type": "v2.initial_quote", "sku": sku, "quantity": qty})
        q = out.get("quote") or {}
        return f"初报：{q.get('name')} 单价 {q.get('unit_price')}，货款 {q.get('goods_total')}，交期 {q.get('lead_days')} 天。"
    if "确认" in t or "工单" in t:
        open_t = [x for x in order_ids.list_open_tickets(agent_id) if x.get("status") == "open"]
        return f"待确认货单 {len(open_t)} 张。请到工单页点「确认订单」；对话不能代替 Gate。"
    if "工具" in t or "place_order" in t.lower():
        names = ", ".join(x["name"] for x in psup.list_tools())
        return (
            f"本厂工具：{names}。\n"
            f"其中 place_order 仅在采购携带 place_order=on（用户明确下单）时写入工单，双方确认后生效。"
        )
    return (
        f"{meta['title']}（{meta['city']}）就绪。可问「优惠政策」「初报」「工具」，"
        f"或到工单页确认订单。目录 SKU：{', '.join(meta['skus'])}。"
    )
