from __future__ import annotations

from typing import Any

from agentlink_runtime.aip_payload import wrap_business
from agentlink_runtime.graph_base import AgentState


def build_quote_request(
    *,
    business_id: str,
    purchase_request: dict[str, Any],
    quote_deadline: str,
) -> dict[str, Any]:
    """预算不得进入出站 RFQ。"""
    payload = {
        "purchase_request_id": purchase_request["purchase_request_id"],
        "version": purchase_request.get("version", 1),
        "product_name": purchase_request["product_name"],
        "specifications": purchase_request.get("specifications", {}),
        "quantity": purchase_request["quantity"],
        "currency": purchase_request.get("currency", "CNY"),
        "tax_included_required": True,
        "delivery_deadline": purchase_request.get("delivery", {}).get("deadline"),
        "quality_requirements": purchase_request.get("quality_requirements", []),
        "quote_deadline": quote_deadline,
    }
    assert "budget" not in payload
    return wrap_business("agentlink.quote_request", business_id, payload)


def compare_quotes(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for q in quotes:
        p = (q.get("payload") or q)
        shipping = p.get("shipping_cost", None)
        rows.append(
            {
                "quote_id": p.get("quote_id"),
                "supplier_agent_id": p.get("supplier_agent_id"),
                "unit_price": p.get("unit_price"),
                "lead_time_days": p.get("lead_time_days"),
                "shipping_cost": shipping,
                "shipping_unknown": shipping is None,
                "strategy_tag": p.get("strategy_tag"),
            }
        )
    rows_sorted = sorted(
        rows,
        key=lambda r: (r["unit_price"] is None, r["unit_price"] or 1e18, r["lead_time_days"] or 1e9),
    )
    return {"quotes": rows_sorted, "note": "shipping_cost null means unknown, not zero"}


def run_buyer_plan(state: AgentState, purchase_request: dict[str, Any]) -> AgentState:
    facts = dict(state.get("working_facts") or {})
    facts["purchase_request"] = purchase_request
    if purchase_request.get("human_approval_status") != "approved":
        state["error"] = "PR_NOT_APPROVED"
        state["outcome"] = {"status": "blocked", "reason": "purchase request not approved"}
        return state
    state["working_facts"] = facts
    state["outcome"] = {"status": "ready_to_rfq"}
    return state


def _resolve_draft_line(
    purchase_request: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[int, str | None, str | None]:
    """按报价行/brief.lines 解析数量与品名；禁止把组合案各行数量加总串进一单。"""
    try:
        from agents.supplier_common.catalog_price import normalize_sku
    except Exception:  # noqa: BLE001
        def normalize_sku(text: str | None) -> str | None:  # type: ignore
            return str(text).strip().upper() if text else None

    prod = payload.get("product") if isinstance(payload.get("product"), dict) else {}
    quote_qty = prod.get("quantity") or payload.get("quantity") or payload.get("qty")
    quote_sku = normalize_sku(
        str(payload.get("sku") or prod.get("sku") or payload.get("product_name") or prod.get("name") or "")
    )
    quote_name = str(payload.get("product_name") or prod.get("name") or payload.get("sku") or "") or None
    lines = purchase_request.get("lines") if isinstance(purchase_request.get("lines"), list) else []

    matched = None
    if lines:
        if quote_sku:
            for ln in lines:
                if not isinstance(ln, dict):
                    continue
                if normalize_sku(str(ln.get("sku") or ln.get("name") or "")) == quote_sku:
                    matched = ln
                    break
        if matched is None and len(lines) == 1 and isinstance(lines[0], dict):
            matched = lines[0]
    if matched is not None:
        try:
            qty = int(float(matched.get("qty") or quote_qty or 1))
        except (TypeError, ValueError):
            qty = int(float(quote_qty or 1))
        name = str(matched.get("name") or matched.get("sku") or quote_name or "")
        sku = normalize_sku(str(matched.get("sku") or name)) or quote_sku
        return max(qty, 1), name or quote_name, sku

    # 无 lines：若 brief 品名是组合展示串，优先用报价自带数量/货价反推，禁止吃加总 quantity
    pname = str(purchase_request.get("product_name") or "")
    looks_combo = (" + " in pname) or ("＋" in pname) or bool(purchase_request.get("combo"))
    if quote_qty is not None:
        try:
            return max(int(float(quote_qty)), 1), quote_name or pname, quote_sku
        except (TypeError, ValueError):
            pass
    if looks_combo:
        gt = payload.get("goods_total")
        unit = payload.get("unit_price")
        try:
            if gt is not None and unit not in (None, 0, 0.0, "0"):
                return max(int(round(float(gt) / float(unit))), 1), quote_name or pname, quote_sku
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        # 最后手段：不要用 brief.quantity（可能是错误加总）
        return 1, quote_name or pname, quote_sku

    try:
        qty = int(float(purchase_request.get("quantity") or quote_qty or 0))
    except (TypeError, ValueError):
        qty = 0
    return max(qty, 1), quote_name or pname, quote_sku


def build_order_draft(
    *,
    business_id: str,
    purchase_request: dict[str, Any],
    selected_quote: dict[str, Any],
) -> dict[str, Any]:
    """生成订单草案（不激活）。运费未知时标注 shipping_unknown。"""
    payload = selected_quote.get("payload") or selected_quote
    shipping = payload.get("shipping_cost")
    if shipping is None and isinstance(payload.get("freight"), dict):
        shipping = payload["freight"].get("amount")
    if shipping is None:
        shipping = payload.get("freight_amount")
    unit = float(payload["unit_price"])
    qty, product_name, sku = _resolve_draft_line(purchase_request, payload)
    goods_total = round(unit * qty, 2)
    # 从报价全量规格或主数据补齐重量/体积，供后续询运
    try:
        from commerce.seat_catalog import product_physical_specs

        physical = product_physical_specs(sku, qty=qty)
    except Exception:  # noqa: BLE001
        physical = {}
    prod = payload.get("product") if isinstance(payload.get("product"), dict) else {}
    weight = (
        payload.get("weight_kg")
        or prod.get("weight_kg")
        or (payload.get("physical_specs") or {}).get("weight_kg")
        or physical.get("weight_kg")
    )
    volume = (
        payload.get("volume_m3")
        or prod.get("volume_m3")
        or (payload.get("physical_specs") or {}).get("volume_m3")
        or physical.get("volume_m3")
    )
    draft = {
        "draft_id": f"draft-{business_id}",
        "business_id": business_id,
        "purchase_request_id": purchase_request.get("purchase_request_id"),
        "supplier_agent_id": payload.get("supplier_agent_id"),
        "quote_id": payload.get("quote_id"),
        "product_name": product_name,
        "sku": sku,
        "quantity": qty,
        "unit_price": unit,
        "currency": payload.get("currency", "CNY"),
        "tax_included": payload.get("tax_included", True),
        "goods_total": goods_total,
        "weight_kg": weight,
        "volume_m3": volume,
        "kg_per_unit": prod.get("kg_per_unit") or physical.get("kg_per_unit"),
        "pack_cm": prod.get("pack_cm") or physical.get("pack_cm"),
        "charge_class": prod.get("charge_class") or physical.get("charge_class"),
        "physical_specs": prod.get("specs") or payload.get("physical_specs") or physical,
        "shipping_cost": shipping,
        "shipping_unknown": shipping is None,
        "status": "ORDER_DRAFT",
        "activate_allowed": False,
        "note": "草案仅供人工确认；activate_order 需 commit + HITL",
    }
    return wrap_business("agentlink.order_draft", business_id, draft)
