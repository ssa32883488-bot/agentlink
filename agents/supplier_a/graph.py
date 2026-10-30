from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from agentlink_runtime.aip_payload import wrap_business
from agentlink_runtime.graph_base import AgentState
from agents.supplier_a.pricing import compute_quote
from agents.supplier_common.freight import attach_freight
from agents.supplier_common.negotiate import dispatch_extra_schemas, enrich_initial_quote


async def run_supplier_pipeline(
    *,
    state: AgentState,
    rfq_envelope: dict[str, Any],
    policy: dict[str, Any],
) -> AgentState:
    """确定性冒烟路径：parse → inventory → price →（被动）物流询运 → emit。"""
    facts = dict(state.get("working_facts") or {})
    schema = rfq_envelope.get("schema_type")
    extra = await dispatch_extra_schemas(state=state, envelope=rfq_envelope, policy=policy)
    if extra is not None:
        return extra
    if schema != "agentlink.quote_request":
        state["error"] = "INVALID_SCHEMA"
        state["outcome"] = {"aip_state": "rejected", "reason": f"unexpected schema_type={schema}"}
        return state

    payload = rfq_envelope.get("payload") or {}
    required = ["purchase_request_id", "quantity", "product_name", "specifications"]
    missing = [k for k in required if k not in payload]
    if missing:
        state["outcome"] = {
            "aip_state": "awaiting-input",
            "clarify": f"missing fields: {', '.join(missing)}",
        }
        return state

    qty = int(payload["quantity"])
    specs = payload.get("specifications") or {}
    priced = compute_quote(
        policy,
        qty,
        product_name=payload.get("product_name"),
        sku=payload.get("sku") or (specs.get("sku") if isinstance(specs, dict) else None),
        specifications=specs if isinstance(specs, dict) else None,
    )
    if not priced.get("catalog_hit"):
        state["outcome"] = {
            "aip_state": "rejected",
            "reason": str(priced.get("reject_reason") or f"本厂目录无此物料: {payload.get('product_name')}"),
        }
        return state
    if not priced["can_fulfill"]:
        state["outcome"] = {
            "aip_state": "rejected",
            "reason": f"insufficient inventory: need {qty}, have {priced['available_quantity']}",
        }
        return state

    quote_id = f"quote-a-{uuid4().hex[:8]}"
    valid_until = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    spec_txt = (
        f"SKU {priced.get('sku')} · 额定承重不低于{specs.get('rated_load_kg_min', '?')}kg"
        if isinstance(specs, dict)
        else str(priced.get("sku"))
    )
    quote_payload = {
        "quote_id": quote_id,
        "purchase_request_id": payload["purchase_request_id"],
        "supplier_agent_id": state.get("agent_id") or "supplier-a",
        "version": 1,
        "status": "initial_quote",
        "product": {
            "name": priced.get("name") or payload["product_name"],
            "sku": priced.get("sku"),
            "specification": spec_txt,
            "quantity": qty,
        },
        "unit_price": priced["unit_price"],
        "currency": priced["currency"],
        "tax_included": priced["tax_included"],
        "available_quantity": priced["available_quantity"],
        "lead_time_days": priced["lead_time_days"],
        "line_qty_discount": priced.get("line_qty_discount"),
        "quality_documents": ["产品参数表"],
        "shipping_cost": None,
        "valid_until": valid_until,
        "conditions": [],
        "strategy_tag": priced["strategy_tag"],
    }
    quote_payload = await attach_freight(
        quote_payload, rfq_payload=payload, state=state, policy=policy
    )
    quote_payload = enrich_initial_quote(
        quote_payload, policy, rfq_payload=payload, priced=priced
    )

    envelope = wrap_business(
        "agentlink.initial_quote",
        state.get("business_id") or rfq_envelope.get("business_id") or "",
        quote_payload,
    )
    facts["last_quote"] = envelope
    state["working_facts"] = facts
    state["outcome"] = {
        "aip_state": "awaiting-completion",
        "product_name": "initial_quote",
        "envelope": envelope,
    }
    return state
