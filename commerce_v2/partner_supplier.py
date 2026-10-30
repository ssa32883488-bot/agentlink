# -*- coding: utf-8 -*-
"""供应智力：初报 / 议价 / 规格 / 交期 / 工单确认 / 组群出价。"""
from __future__ import annotations

from typing import Any

from commerce_v2.catalog import SUPPLIERS
from commerce_v2 import order_sync
from commerce_v2.supplier_tools import is_place_order_on, tool_catalog


def _quote_line(agent_id: str, sku: str, qty: float, *, apply_promo: bool) -> dict[str, Any]:
    meta = SUPPLIERS[agent_id]
    item = meta["skus"][sku]
    unit = float(item["list_price"])
    promo = item.get("promo") or {}
    reason = None
    final = unit
    goods_adj = None
    if apply_promo and promo.get("type") == "qty_discount" and qty >= float(promo.get("min_qty") or 0):
        final = round(unit * float(promo["rate"]), 4)
        reason = promo.get("reason")
    elif apply_promo and promo.get("type") == "amount_off":
        goods = unit * qty
        if goods >= float(promo.get("min_amount") or 0):
            reason = promo.get("reason")
            goods_adj = round(goods - float(promo.get("off") or 0), 2)
    goods = goods_adj if goods_adj is not None else round(final * qty, 2)
    return {
        "supplier_agent_id": agent_id,
        "sku": sku,
        "name": item["name"],
        "qty": qty,
        "unit_price": final,
        "list_price": unit,
        "goods_total": goods,
        "spec": item["spec"],
        "lead_days": item["lead_days"],
        "promo_applied": bool(reason),
        "promo_reason": reason or ("无优惠政策，返回挂牌价" if apply_promo else None),
        "city": meta["city"],
    }


def handle_envelope(agent_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
    schema = str(envelope.get("schema_type") or "")
    sku = str(envelope.get("sku") or envelope.get("material_code") or "")
    qty = float(envelope.get("quantity") or envelope.get("qty") or 0)
    meta = SUPPLIERS.get(agent_id)
    if not meta:
        return {"ok": False, "schema_type": "v2.error", "error": f"unknown supplier {agent_id}"}
    if schema in ("agentlink.quote_request", "v2.initial_quote", "initial_quote"):
        if sku not in meta["skus"]:
            return {"ok": False, "schema_type": "v2.quote_error", "error": f"{agent_id} 无 SKU {sku}"}
        return {"ok": True, "schema_type": "v2.initial_quote", "quote": _quote_line(agent_id, sku, qty, apply_promo=False)}
    if schema in ("v2.promo_query", "promo_query", "promotions_query", "ask_promo"):
        # 直接回答「有什么优惠政策」——公示政策，不靠虚高数量试探
        items = []
        for k, v in meta["skus"].items():
            if sku and k != sku:
                continue
            p = v.get("promo") or {}
            if p and p.get("type") not in (None, "none"):
                items.append(
                    {
                        "sku": k,
                        "name": v.get("name"),
                        "promo": p,
                        "reason": p.get("reason") or str(p),
                    }
                )
            else:
                items.append(
                    {
                        "sku": k,
                        "name": v.get("name"),
                        "promo": {"type": "none"},
                        "reason": "无优惠政策，返回挂牌价",
                    }
                )
        summary = "；".join(f"{it['name']}：{it['reason']}" for it in items) or "无公示优惠"
        return {
            "ok": True,
            "schema_type": "v2.promo_answer",
            "supplier_agent_id": agent_id,
            "promotions": items,
            "message": f"{meta.get('title')}公示优惠：{summary}",
            "question": envelope.get("question") or "有什么优惠政策",
        }
    if schema in ("agentlink.bargain_round", "v2.bargain", "bargain"):
        if sku not in meta["skus"]:
            return {"ok": False, "schema_type": "v2.error", "error": f"{agent_id} 无 SKU {sku}"}
        # 按买方真实需求量套用已公示优惠（不是虚增数量试探）
        return {"ok": True, "schema_type": "v2.bargain_quote", "quote": _quote_line(agent_id, sku, qty, apply_promo=True)}
    if schema in ("v2.spec_query", "spec_query"):
        if sku not in meta["skus"]:
            return {"ok": False, "schema_type": "v2.error", "error": "sku not found"}
        item = meta["skus"][sku]
        return {
            "ok": True,
            "schema_type": "v2.spec_answer",
            "spec": item["spec"],
            "name": item["name"],
            "lead_days": item["lead_days"],
            "ship_from": meta["city"],
        }
    if schema in ("v2.place_order", "place_order", "v2.order_sync", "order_sync"):
        # 供应商工具 place_order：仅当采购携带 place_order=on（用户明确下单）才落单
        order = envelope.get("order") if isinstance(envelope.get("order"), dict) else None
        if not order:
            order = {
                "order_id": envelope.get("order_id"),
                "case_id": envelope.get("case_id"),
                "buyer_id": envelope.get("buyer_id"),
                "supplier_id": envelope.get("supplier_id") or agent_id,
                "sku": envelope.get("sku") or envelope.get("material_code"),
                "name": envelope.get("name"),
                "qty": envelope.get("quantity") or envelope.get("qty"),
                "unit_price": envelope.get("unit_price"),
                "goods_total": envelope.get("goods_total"),
                "title": envelope.get("title")
                or f"货单 · {envelope.get('name') or envelope.get('sku')} × {envelope.get('quantity') or envelope.get('qty') or '?'} · {agent_id}",
                "buyer_ack": bool(envelope.get("buyer_ack")),
                "supplier_ack": bool(envelope.get("supplier_ack")),
                "effective": bool(envelope.get("effective")),
            }
        flag = envelope.get("place_order")
        if flag is None and isinstance(order, dict):
            flag = order.get("place_order")
        existing = None
        oid = (order or {}).get("order_id")
        if oid:
            from commerce_v2 import order_ids

            existing = order_ids.get_order(str(oid))
        # 新建必须 on；已有单的确认态回写可无 on
        if not existing and not is_place_order_on(flag):
            return {
                "ok": False,
                "schema_type": "v2.place_order_rejected",
                "error": "place_order 未开启：需用户明确下单后由采购携带 place_order=on",
                "tool": "place_order",
                "place_order": "off",
            }
        if order.get("order_id"):
            order.setdefault("supplier_id", agent_id)
            if existing or is_place_order_on(flag):
                order["place_order"] = "on"
            order_sync.apply_order(order, require_place_on_for_create=True)
        return {
            "ok": True,
            "schema_type": "v2.order_received",
            "order_id": order.get("order_id"),
            "tool": "place_order",
            "place_order": "on",
            "message": "已调用供应商工具 place_order：订单写入供应侧工单，待双方确认",
        }
    if schema in ("v2.group_bid", "group_bid"):
        if sku not in meta["skus"]:
            return {"ok": False, "schema_type": "v2.error", "error": "cannot bid"}
        return {"ok": True, "schema_type": "v2.group_bid", "bid": _quote_line(agent_id, sku, qty, apply_promo=True)}
    return {"ok": False, "schema_type": "v2.error", "error": f"unsupported schema {schema}"}


def list_tools() -> list[dict[str, Any]]:
    return tool_catalog()


def pipeline(*, state, envelope: dict[str, Any], policy: dict[str, Any]):
    agent_id = state.get("agent_id") if isinstance(state, dict) else getattr(state, "agent_id", "")
    out = handle_envelope(str(agent_id), envelope)
    if not out.get("ok"):
        state["outcome"] = {"aip_state": "failed", "reason": out.get("error") or "failed"}
        return state
    state["outcome"] = {"envelope": out, "product_name": out.get("schema_type") or "v2"}
    return state
