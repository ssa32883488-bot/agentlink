"""供应商侧：议价 / 匿名竞价 / 合同确认（各供应商 graph 复用）。

议价原则：不以「死压单价」为主；用满减门槛、跨省补贴、交期/库存交换条件，
并给出可讨论的 counter_options。预算数字从不要求买方提供。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from agentlink_runtime.aip_payload import wrap_business
from agentlink_runtime.graph_base import AgentState
from agents.supplier_a.pricing import compute_quote
from agents.supplier_common.freight import attach_freight
from agents.supplier_common.promo import (
    build_bargain_narrative,
    goodwill_unit_price,
    promo_leverage_amount,
    settle_quote_economics,
)


async def handle_bargain_round(
    *,
    state: AgentState,
    envelope: dict[str, Any],
    policy: dict[str, Any],
) -> AgentState:
    payload = envelope.get("payload") or {}
    req_qty = int(payload.get("quantity") or 1)
    specs = payload.get("specifications") if isinstance(payload.get("specifications"), dict) else {}
    priced = compute_quote(
        policy,
        req_qty,
        product_name=payload.get("product_name"),
        sku=payload.get("sku") or specs.get("sku"),
        specifications=specs,
    )
    avail = int(priced.get("available_quantity") or policy.get("available_quantity") or req_qty)
    qty = min(req_qty, avail) if avail > 0 else req_qty
    prev = payload.get("previous_unit_price")
    base = float(prev) if prev is not None else float(priced["unit_price"])
    # 无私下让价：单价保持挂牌（或上一轮报价）；优惠只结算 promotions
    new_price = goodwill_unit_price(policy, previous_unit=base, quantity=qty)
    sku_code = str(priced.get("sku") or payload.get("sku") or "")

    # 先组草稿，合入运费后再结算满减/补贴；bargain_room = 优惠杠杆
    draft = {
        "quote_id": f"quote-neg-{uuid4().hex[:8]}",
        "supplier_agent_id": state.get("agent_id"),
        "status": "bargain_offer",
        "unit_price": new_price,
        "currency": "CNY",
        "tax_included": True,
        "lead_time_days": priced["lead_time_days"],
        "available_quantity": priced["available_quantity"],
        "bargain_room": 0.0,
        "valid_until": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        "goal_echo": payload.get("goal_text"),
        "product": {
            "name": priced.get("name") or payload.get("product_name") or "item",
            "sku": sku_code or None,
            "quantity": qty,
            "requested_quantity": req_qty,
            "specification": str(payload.get("specifications") or {}),
        },
        "strategy_tag": priced.get("strategy_tag"),
        "need_freight": payload.get("need_freight", True),
        "inventory_capped": qty < req_qty,
        "inventory_note": (
            f"可售 {avail}，按 {qty} 件议价（请求 {req_qty}）；超额部分建议拆单或改采"
            if qty < req_qty
            else None
        ),
    }
    draft = enrich_product_block(draft, priced=priced, rfq_payload=payload)
    # 议价默认不代询运费（货物流与物流流分离）；仅当买方明确 need_freight 时才合入
    if payload.get("need_freight"):
        draft = await attach_freight(draft, rfq_payload=payload, state=state, policy=policy)
    freight = draft.get("shipping_cost")
    if freight is None and isinstance(draft.get("freight"), dict):
        freight = draft["freight"].get("amount")
    if freight is None:
        freight = draft.get("freight_amount")

    econ = settle_quote_economics(
        policy,
        qty=qty,
        unit_price=new_price,
        freight=float(freight) if freight is not None else None,
        rfq_payload=payload,
        sku=sku_code,
    )
    narrative = build_bargain_narrative(
        policy, economics=econ, goal_text=payload.get("goal_text")
    )

    # 若买方目标暗示「凑门槛 / 加量」，可按下一档满减量给出对照价
    alt_econ = None
    gap = econ.get("next_tier")
    if gap:
        # 始终附带「凑满减」对照，便于采购侧方案推演；不要求预算
        alt_qty = int(gap["target_qty"])
        alt_price = goodwill_unit_price(policy, previous_unit=base, quantity=alt_qty)
        # 运费粗估：按件数比例放大（方案层会再精细）
        alt_freight = None
        if freight is not None and qty > 0:
            alt_freight = round(float(freight) * (alt_qty / qty), 2)
        alt_econ = settle_quote_economics(
            policy,
            qty=alt_qty,
            unit_price=alt_price,
            freight=alt_freight,
            rfq_payload=payload,
            sku=sku_code,
        )

    # 议价轮才披露活动：结构化 policy，避免采购侧读到 policy=null
    gap = econ.get("next_tier") if isinstance(econ.get("next_tier"), dict) else None
    reach_summary = None
    if isinstance(alt_econ, dict):
        reach_summary = {
            "target_qty": alt_econ.get("quantity") or (gap or {}).get("target_qty"),
            "list_goods_total": round(
                float(alt_econ.get("list_unit_price") or new_price)
                * float(alt_econ.get("quantity") or 0),
                2,
            ),
            "goods_after_promo": alt_econ.get("goods_after_promo"),
            "unit_after_promo": alt_econ.get("unit_price"),
            "hint": (gap or {}).get("hint"),
            "label": ((gap or {}).get("tier") or {}).get("label") if isinstance(gap, dict) else None,
        }
    policy_public = {
        "disclosed": True,
        "hints": narrative["policy_hints"],
        "talk_track": narrative["talk_track"],
        "next_tier": gap,
        "reach_example": reach_summary,
        "applied": {
            "line_qty_save": econ.get("line_qty_save"),
            "full_reduction_save": econ.get("full_reduction_save"),
            "goods_after_promo": econ.get("goods_after_promo"),
        },
    }
    out = {
        **draft,
        "unit_price": new_price,
        "bargain_room": promo_leverage_amount(econ),
        "goods_total": econ["goods_total"],
        "full_reduction_save": econ["full_reduction_save"],
        "goods_after_promo": econ["goods_after_promo"],
        "promo_settlement": econ,
        "policy": policy_public,
        "policy_hints": narrative["policy_hints"],
        "talk_track": narrative["talk_track"],
        "counter_options": narrative["counter_options"],
        "negotiation_style": narrative["negotiation_style"],
        "reach_promo_preview": alt_econ,
        "promotions_disclosed": True,
        "note": "无私下底价；议价只走活动门槛与补贴路径；不索取买方预算",
        "pricing_mode": "list_plus_promo_only",
    }
    state["outcome"] = {
        "aip_state": "awaiting-completion",
        "product_name": "bargain_offer",
        "envelope": wrap_business(
            "agentlink.bargain_offer",
            state.get("business_id") or envelope.get("business_id") or "",
            out,
        ),
    }
    return state


def handle_blind_bid(
    *,
    state: AgentState,
    envelope: dict[str, Any],
    policy: dict[str, Any],
) -> AgentState:
    payload = envelope.get("payload") or {}
    qty = int(payload.get("quantity") or 1)
    specs = payload.get("specifications") if isinstance(payload.get("specifications"), dict) else {}
    priced = compute_quote(
        policy,
        qty,
        product_name=payload.get("product_name"),
        sku=payload.get("sku") or specs.get("sku"),
        specifications=specs,
    )
    # 竞价亦不砍挂牌价；优惠仍只结算 promotions
    bid_price = round(float(priced["unit_price"]), 2)
    econ = settle_quote_economics(
        policy,
        qty=qty,
        unit_price=bid_price,
        freight=None,
        rfq_payload=payload,
        sku=str(priced.get("sku") or ""),
    )
    out = {
        "bid_id": f"bid-{uuid4().hex[:8]}",
        "auction_id": payload.get("auction_id"),
        "supplier_agent_id": state.get("agent_id"),
        "unit_price": bid_price,
        "currency": "CNY",
        "lead_time_days": priced["lead_time_days"],
        "sealed": True,
        "valid_until": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        "policy_hints": econ.get("policy_hints") or [],
    }
    state["outcome"] = {
        "aip_state": "awaiting-completion",
        "product_name": "blind_bid",
        "envelope": wrap_business(
            "agentlink.blind_bid_offer",
            state.get("business_id") or envelope.get("business_id") or "",
            out,
        ),
    }
    return state


def handle_contract_ack(
    *,
    state: AgentState,
    envelope: dict[str, Any],
    policy: dict[str, Any],
) -> AgentState:
    payload = envelope.get("payload") or {}
    out = {
        "contract_id": payload.get("contract_id"),
        "party": "supplier",
        "action": "confirmed",
        "supplier_agent_id": state.get("agent_id"),
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "note": "供应商侧演示自动确认（生产应走人类 HITL）",
    }
    state["outcome"] = {
        "aip_state": "awaiting-completion",
        "product_name": "contract_ack",
        "envelope": wrap_business(
            "agentlink.contract_ack_result",
            state.get("business_id") or envelope.get("business_id") or "",
            out,
        ),
    }
    return state


async def dispatch_extra_schemas(
    *,
    state: AgentState,
    envelope: dict[str, Any],
    policy: dict[str, Any],
) -> AgentState | None:
    schema = envelope.get("schema_type")
    if schema == "agentlink.bargain_round":
        return await handle_bargain_round(state=state, envelope=envelope, policy=policy)
    if schema == "agentlink.blind_bid":
        return handle_blind_bid(state=state, envelope=envelope, policy=policy)
    if schema == "agentlink.contract_ack":
        return handle_contract_ack(state=state, envelope=envelope, policy=policy)
    return None


def enrich_product_block(
    quote_payload: dict[str, Any],
    *,
    priced: dict[str, Any] | None = None,
    rfq_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """报价 product 块写入全量规格（价格侧字段 + 重量/体积/包装）。"""
    from commerce.seat_catalog import product_physical_specs

    prod = dict(quote_payload.get("product") or {}) if isinstance(quote_payload.get("product"), dict) else {}
    qty = int(prod.get("quantity") or quote_payload.get("quantity") or (rfq_payload or {}).get("quantity") or 1)
    sku = str(
        prod.get("sku")
        or (priced or {}).get("sku")
        or quote_payload.get("sku")
        or (rfq_payload or {}).get("sku")
        or ""
    )
    physical = dict((priced or {}).get("physical_specs") or {}) or product_physical_specs(sku, qty=qty)
    # RFQ 侧自定义规格并入，不覆盖物理主数据
    req_specs = (rfq_payload or {}).get("specifications")
    if isinstance(req_specs, dict) and req_specs:
        physical = {**physical, "buyer_specifications": req_specs}
    prod.update(
        {
            "name": prod.get("name") or physical.get("name") or (priced or {}).get("name") or sku,
            "sku": sku or physical.get("sku"),
            "quantity": qty,
            "unit": physical.get("unit") or prod.get("unit") or "件",
            "pack_cm": physical.get("pack_cm"),
            "volume_m3_unit": physical.get("volume_m3_unit"),
            "volume_m3": physical.get("volume_m3"),
            "kg_per_unit": physical.get("kg_per_unit"),
            "weight_kg": physical.get("weight_kg"),
            "charge_class": physical.get("charge_class"),
            "note": physical.get("note"),
            "specs": physical,
        }
    )
    # 兼容旧字段：specification 给人看的摘要
    if not prod.get("specification"):
        bits = [f"SKU {prod.get('sku')}"]
        if prod.get("weight_kg") is not None:
            bits.append(f"重量 {prod['weight_kg']}kg")
        if prod.get("volume_m3") is not None:
            bits.append(f"体积 {prod['volume_m3']}m³")
        if prod.get("pack_cm"):
            bits.append(f"包装 {prod['pack_cm']}cm")
        prod["specification"] = " · ".join(bits)
    quote_payload["product"] = prod
    quote_payload["sku"] = prod.get("sku")
    quote_payload["product_name"] = prod.get("name")
    quote_payload["weight_kg"] = prod.get("weight_kg")
    quote_payload["volume_m3"] = prod.get("volume_m3")
    quote_payload["physical_specs"] = physical
    return quote_payload


def enrich_initial_quote(
    quote_payload: dict[str, Any],
    policy: dict[str, Any],
    rfq_payload: dict[str, Any] | None = None,
    priced: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """初轮报价：只回挂牌价 + 产品规格/体积重量；不暴露优惠政策（优惠留到议价轮）。"""
    _ = policy  # 初询不读 promotions
    quote_payload = enrich_product_block(
        quote_payload, priced=priced, rfq_payload=rfq_payload
    )
    # 明确清空可能被上游带入的优惠字段，避免初询泄密
    quote_payload.pop("policy_hints", None)
    quote_payload.pop("promo_preview", None)
    quote_payload.pop("promo_settlement", None)
    quote_payload.pop("reach_promo_preview", None)
    quote_payload.pop("counter_options", None)
    quote_payload.pop("talk_track", None)
    quote_payload["bargain_room"] = None
    quote_payload["promotions_disclosed"] = False
    quote_payload["policy"] = None
    quote_payload["negotiation_style"] = "list_price_first"
    quote_payload["pricing_mode"] = "list_price_only"
    note = str(quote_payload.get("note") or "").strip()
    seal = "初询仅挂牌价与产品规格；优惠政策请议价时再询"
    quote_payload["note"] = f"{note}；{seal}" if note else seal
    return quote_payload
