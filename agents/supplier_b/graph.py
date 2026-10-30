from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from agentlink_runtime.aip_payload import wrap_business
from agentlink_runtime.graph_base import AgentState
from agents.supplier_common.freight import attach_freight
from agents.supplier_common.negotiate import dispatch_extra_schemas, enrich_initial_quote


async def run_supplier_b_pipeline(
    *,
    state: AgentState,
    envelope: dict[str, Any],
    policy: dict[str, Any],
) -> AgentState:
    extra = await dispatch_extra_schemas(state=state, envelope=envelope, policy=policy)
    if extra is not None:
        return extra
    if envelope.get("schema_type") != "agentlink.quote_request":
        state["outcome"] = {
            "aip_state": "rejected",
            "reason": f"unexpected schema_type={envelope.get('schema_type')}",
        }
        return state

    payload = envelope.get("payload") or {}
    required = ["purchase_request_id", "quantity", "product_name", "specifications"]
    missing = [k for k in required if k not in payload]
    if missing:
        state["outcome"] = {
            "aip_state": "awaiting-input",
            "clarify": f"missing fields: {', '.join(missing)}",
        }
        return state

    specs = payload.get("specifications") or {}
    qty = int(payload["quantity"])
    from agents.supplier_a.pricing import compute_quote

    priced = compute_quote(
        policy,
        qty,
        product_name=payload.get("product_name"),
        sku=payload.get("sku") or specs.get("sku") or specs.get("material_code"),
        specifications=specs,
    )
    if not priced.get("catalog_hit"):
        state["outcome"] = {
            "aip_state": "rejected",
            "reason": str(priced.get("reject_reason") or f"本厂目录无此物料: {payload.get('product_name')}"),
        }
        return state

    need = list(policy.get("min_custom_fields") or [])
    miss_spec = [k for k in need if k not in specs or specs.get(k) in (None, "")]
    if miss_spec:
        state["outcome"] = {
            "aip_state": "awaiting-input",
            "clarify": f"custom spec incomplete, need: {', '.join(miss_spec)}",
        }
        return state

    moq = int(priced.get("moq") or policy.get("moq", 1))
    if qty < moq:
        state["outcome"] = {
            "aip_state": "rejected",
            "reason": f"below MOQ: need>={moq}, got {qty}",
        }
        return state

    quote_payload = {
        "quote_id": f"quote-b-{uuid4().hex[:8]}",
        "purchase_request_id": payload["purchase_request_id"],
        "supplier_agent_id": state.get("agent_id") or "supplier-b",
        "version": 1,
        "status": "initial_quote",
        "product": {
            "name": priced.get("name") or payload["product_name"],
            "sku": priced.get("sku"),
            "specification": specs,
            "quantity": qty,
            "custom": True,
        },
        "unit_price": priced["unit_price"],
        "currency": "CNY",
        "tax_included": bool(policy.get("default_tax_included", True)),
        "available_quantity": priced["available_quantity"],
        "lead_time_days": priced["lead_time_days"],
        "moq": moq,
        "quality_documents": ["定制工艺确认单"],
        "shipping_cost": None,
        "valid_until": (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat(),
        "conditions": ["软装件需确认面料/颜色后排产"],
        "strategy_tag": policy.get("strategy_tag", "custom-moq"),
    }
    quote_payload = await attach_freight(
        quote_payload, rfq_payload=payload, state=state, policy=policy
    )
    quote_payload = enrich_initial_quote(
        quote_payload, policy, rfq_payload=payload, priced=priced
    )
    state["outcome"] = {
        "aip_state": "awaiting-completion",
        "product_name": "initial_quote",
        "envelope": wrap_business(
            "agentlink.initial_quote",
            state.get("business_id") or envelope.get("business_id") or "",
            quote_payload,
        ),
    }
    return state
