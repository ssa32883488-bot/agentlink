# -*- coding: utf-8 -*-
"""物流智力：必填清单、运力方案、确认。"""
from __future__ import annotations

from typing import Any

from commerce_v2.catalog import LOGISTICS_REQUIRED
from commerce_v2 import order_sync


def handle_envelope(agent_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
    schema = str(envelope.get("schema_type") or "")
    if schema in ("v2.logistics_schema", "logistics_schema", "shipping_requirements"):
        return {
            "ok": True,
            "schema_type": "v2.logistics_schema",
            "required_fields": LOGISTICS_REQUIRED,
            "message": "下运单前请提供以下字段；清单外字段不阻塞下单。",
        }
    if schema in ("v2.logistics_quote", "shipping_request", "agentlink.shipping_request"):
        missing = [f["key"] for f in LOGISTICS_REQUIRED if not envelope.get(f["key"])]
        if missing:
            return {
                "ok": False,
                "schema_type": "v2.logistics_need_fields",
                "missing": missing,
                "required_fields": LOGISTICS_REQUIRED,
            }
        origin = str(envelope.get("origin") or "")
        dest = str(envelope.get("destination") or "")
        qty = float(envelope.get("chargeable_qty") or envelope.get("quantity") or 1)
        # 简易计费：基数 200 + 件数*1.2 + 跨城附加
        base = 200.0 + qty * 1.2
        if origin and dest and origin != dest:
            base += 80.0
        scheme = {
            "service": "标准公路",
            "origin": origin,
            "destination": dest,
            "eta_days": 2 if origin == dest else 3,
            "freight": round(base, 2),
            "goods_spec": envelope.get("goods_spec"),
            "ship_date": envelope.get("ship_date"),
        }
        return {"ok": True, "schema_type": "v2.logistics_scheme", "scheme": scheme}
    if schema in ("v2.place_logistics", "place_logistics", "v2.logistics_sync", "logistics_sync"):
        row = envelope.get("logistics") if isinstance(envelope.get("logistics"), dict) else None
        if not row:
            row = {
                "logistics_id": envelope.get("logistics_id"),
                "order_id": envelope.get("order_id"),
                "buyer_id": envelope.get("buyer_id"),
                "supplier_id": envelope.get("supplier_id"),
                "title": envelope.get("title") or f"物流单 · {envelope.get('logistics_id')}",
                "scheme": envelope.get("scheme"),
                "fields": envelope.get("fields"),
                "buyer_ack": bool(envelope.get("buyer_ack")),
                "logistics_ack": bool(envelope.get("logistics_ack")),
                "effective": bool(envelope.get("effective")),
            }
        if row.get("logistics_id"):
            order_sync.apply_logistics(row)
        return {
            "ok": True,
            "schema_type": "v2.logistics_received",
            "logistics_id": row.get("logistics_id"),
            "message": "物流单已接收并写入工单，待双方确认",
        }
    return {"ok": False, "schema_type": "v2.error", "error": f"unsupported schema {schema}"}


def pipeline(*, state, envelope: dict[str, Any], policy: dict[str, Any]):
    out = handle_envelope(str(state.get("agent_id") or "logistics"), envelope)
    if not out.get("ok") and out.get("schema_type") != "v2.logistics_need_fields":
        state["outcome"] = {"aip_state": "failed", "reason": out.get("error") or "failed"}
        return state
    # need_fields 仍作为结构化回执返回，便于采购补齐
    state["outcome"] = {"envelope": out, "product_name": out.get("schema_type") or "v2-logistics"}
    return state
