"""采购商A 对话：规则抽槽（可后换 LLM）。"""
from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncIterator, Awaitable, Callable

from commerce import buyer_service as bs

RfqFn = Callable[[list[dict[str, Any]]], Awaitable[dict[str, Any]]]

def _format_rfq_reply(result: dict[str, Any]) -> str:
    ok = result.get("quote_count", 0)
    lines = [
        f"已按缺口向供应商发起询价，成功收到 {ok} 份报价。",
        f"业务单号：{result.get('business_id')}",
        "",
        "报价明细：",
    ]
    for r in result.get("results") or []:
        q = r.get("quote") or {}
        pay = q.get("payload") or q
        product = pay.get("product") or {}
        name = product.get("name") or r.get("material_code") or "—"
        qty = product.get("quantity", "—")
        price = pay.get("unit_price", "—")
        lead = pay.get("lead_time_days", "—")
        avail = pay.get("available_quantity", "—")
        supplier = r.get("supplier") or pay.get("supplier_agent_id") or "—"
        code = r.get("material_code") or "—"
        if r.get("quote"):
            lines.append(
                f"· {supplier} | {name}（{code}） ×{qty} @ ¥{price} | 交期 {lead} 天 | 可供 {avail}"
            )
        else:
            state = r.get("state") or r.get("message") or "失败"
            lines.append(f"· {supplier} | {code} — 未拿到报价（{state}）")
    if result.get("errors"):
        lines.append("")
        lines.append("部分失败：")
        lines.extend(f"- {e}" for e in result["errors"][:5])
    return "\n".join(lines)


async def handle_buyer_chat(text: str, *, run_rfq: RfqFn | None = None) -> dict[str, Any]:
    text = (text or "").strip()
    bs.append_conversation("user", text)
    low = text.lower()

    # 查库存
    if re.search(r"库存|还有多少|原料", text):
        inv = bs.list_inventory()
        low_rows = [i for i in inv if i.get("low")]
        lines = [f"- {i['name']}: 可用 {i['available']}{i['unit']}（安全 {i['safety_stock']}）"
                 + (" ⚠低于安全线" if i.get("low") else "") for i in inv]
        reply = "当前原料库存：\n" + "\n".join(lines)
        if low_rows:
            reply += "\n\n可说「按缺口询价」向上游补货。"
        bs.append_conversation("assistant", reply, {"intent": "query_inventory"})
        return {"reply": reply, "intent": "query_inventory", "data": {"inventory": inv}}

    # 查销售订单
    if re.search(r"订单|卖货|销售单", text):
        orders = bs.list_sales_orders(20)
        if not orders:
            reply = "暂无销售订单。可在座椅商城下单。"
        else:
            lines = [f"- {o['id']} {o['sku']} ×{o['qty']} ¥{o['amount']} ({o['status']})" for o in orders]
            reply = "最近销售订单：\n" + "\n".join(lines)
        bs.append_conversation("assistant", reply, {"intent": "query_orders"})
        return {"reply": reply, "intent": "query_orders", "data": {"orders": orders}}

    # 查通知
    if re.search(r"通知|告警|提醒", text):
        notes = bs.list_notifications(limit=10)
        if not notes:
            reply = "暂无通知。"
        else:
            lines = [f"- [{'未读' if not n['read'] else '已读'}] {n['title']}" for n in notes]
            reply = "通知中心：\n" + "\n".join(lines)
        bs.append_conversation("assistant", reply, {"intent": "query_notifications"})
        return {"reply": reply, "intent": "query_notifications", "data": {"notifications": notes}}

    # 按缺口询价 / 补货
    if re.search(r"按缺口询价|缺口询价|去询价|补货|询价|问供应商", text):
        payload = bs.latest_shortage_payload()
        if not payload or not payload.get("shortages"):
            # 无告警时：对所有低于安全线的料询价
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
            if not shortages:
                reply = "当前没有原料缺口，无需询价。"
                bs.append_conversation("assistant", reply, {"intent": "rfq_none"})
                return {"reply": reply, "intent": "rfq_none"}
        else:
            shortages = bs.materials_for_rfq_from_shortage(payload)

        if run_rfq is None:
            reply = "询价通道未就绪，请稍后重试。"
            bs.append_conversation("assistant", reply)
            return {"reply": reply, "intent": "rfq_error"}

        result = await run_rfq(shortages)
        reply = _format_rfq_reply(result)
        bs.append_conversation("assistant", reply, {"intent": "rfq", "result": result})
        return {"reply": reply, "intent": "rfq", "data": result}

    reply = (
        "我是采购商A助手。你可以试：\n"
        "· 查库存 / 查订单 / 查通知\n"
        "· 按缺口询价（或：补货、问供应商）\n"
        "座椅商城客户下单后若原料不足，通知中心会提醒你。"
    )
    bs.append_conversation("assistant", reply, {"intent": "help"})
    return {"reply": reply, "intent": "help"}


async def stream_buyer_chat(text: str, *, run_rfq: RfqFn | None = None) -> AsyncIterator[dict[str, Any]]:
    """规则引擎伪流式：先算完整结果，再按小块推送 token。"""
    yield {"type": "status", "text": "处理中…", "engine": "rules"}
    out = await handle_buyer_chat(text, run_rfq=run_rfq)
    reply = str(out.get("reply") or "")
    chunk = 12
    for i in range(0, len(reply), chunk):
        yield {"type": "token", "text": reply[i : i + chunk]}
        await asyncio.sleep(0.01)
    done = {"type": "done", **out, "engine": "rules"}
    yield done
