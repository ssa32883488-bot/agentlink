from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from agentlink_runtime.aip_payload import wrap_business
from agentlink_runtime.graph_base import AgentState
from agents.supplier_a.pricing import compute_quote
from agents.supplier_common.freight import attach_freight
from agents.supplier_common.negotiate import dispatch_extra_schemas, enrich_initial_quote


async def run_supplier_c_pipeline(
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
    alternatives: list[dict[str, Any]] = []
    split_plan: list[dict[str, Any]] | None = None

    if not priced["can_fulfill"]:
        for alt in policy.get("substitutes") or []:
            if int(alt.get("available_quantity", 0)) >= qty:
                alternatives.append(
                    {
                        "sku": alt["sku"],
                        "name": alt["name"],
                        "rated_load_kg_min": alt.get("rated_load_kg_min"),
                        "unit_price": alt["unit_price"],
                        "available_quantity": alt["available_quantity"],
                        "lead_time_days": alt["lead_time_days"],
                        "note": "equivalence substitute from own catalog",
                    }
                )
        avail = int(priced["available_quantity"])
        if avail > 0:
            days = list(policy.get("split_batch_days") or [5, 12])
            split_plan = [
                {"quantity": avail, "eta_days": days[0]},
                {"quantity": qty - avail, "eta_days": days[1] if len(days) > 1 else days[0] + 7},
            ]
        if not alternatives and not split_plan:
            state["outcome"] = {
                "aip_state": "rejected",
                "reason": f"insufficient inventory and no substitute: need {qty}, have {avail}",
            }
            return state

    quote_payload = {
        "quote_id": f"quote-c-{uuid4().hex[:8]}",
        "purchase_request_id": payload["purchase_request_id"],
        "supplier_agent_id": state.get("agent_id") or "supplier-c",
        "version": 1,
        "status": "initial_quote",
        "product": {
            "name": priced.get("name") or payload["product_name"],
            "sku": priced.get("sku"),
            "specification": f"SKU {priced.get('sku')} · 额定承重不低于{(specs or {}).get('rated_load_kg_min', '?')}kg",
            "quantity": qty,
        },
        "unit_price": priced["unit_price"],
        "currency": priced["currency"],
        "tax_included": priced["tax_included"],
        "available_quantity": priced["available_quantity"],
        "lead_time_days": priced["lead_time_days"],
        "line_qty_discount": priced.get("line_qty_discount"),
        "can_fulfill_full": priced["can_fulfill"],
        "alternatives": alternatives,
        "split_fulfillment_plan": split_plan,
        "quality_documents": ["产品参数表"],
        "shipping_cost": None,
        "valid_until": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "conditions": ["紧张库存；替代/分批方案见 alternatives / split_fulfillment_plan"],
        "strategy_tag": policy.get("strategy_tag", "scarce-substitute"),
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
