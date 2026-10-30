"""供应侧被动物流：discover.logistics → AIP 询运 → 合入货+运报价。"""
from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from agentlink_runtime.aip_client_util import aip_start_structured
from agentlink_runtime.aip_payload import wrap_business
from agentlink_runtime.graph_base import AgentState
from commerce.discovery import discover_logistics
from commerce.merchant import profile as merchant_profile


def _want_freight(rfq_payload: dict[str, Any]) -> bool:
    v = rfq_payload.get("need_freight")
    if v is None:
        return True  # V1 默认货+运
    return bool(v)


def _dest_info(rfq_payload: dict[str, Any], policy: dict[str, Any]) -> tuple[str, str | None]:
    delivery = rfq_payload.get("delivery") if isinstance(rfq_payload.get("delivery"), dict) else {}
    dest = rfq_payload.get("destination") if isinstance(rfq_payload.get("destination"), dict) else {}
    postal = str(
        rfq_payload.get("postal_code")
        or dest.get("postal_code")
        or delivery.get("postal_code")
        or policy.get("default_dest_postal")
        or "071000"
    )
    city = dest.get("city") or delivery.get("city")
    return postal, (str(city).strip() if city else None)


def _origin_city(policy: dict[str, Any], agent_id: str) -> str:
    m = policy.get("merchant") if isinstance(policy.get("merchant"), dict) else {}
    city = policy.get("ship_from_city") or m.get("city") or merchant_profile(agent_id).get("ship_from_city")
    return str(city or "沧州")


def _weight_kg(rfq_payload: dict[str, Any], policy: dict[str, Any], qty: float) -> float:
    if rfq_payload.get("weight_kg") is not None:
        try:
            return float(rfq_payload["weight_kg"])
        except (TypeError, ValueError):
            pass
    try:
        from commerce.seat_catalog import material_by_code
        from agents.supplier_common.catalog_price import normalize_sku

        code = normalize_sku(
            str(
                rfq_payload.get("sku")
                or (rfq_payload.get("specifications") or {}).get("sku")
                or (rfq_payload.get("specifications") or {}).get("material_code")
                or rfq_payload.get("product_name")
                or ""
            )
        )
        mat = material_by_code(code) if code else None
        if mat and mat.get("kg_per_unit") is not None:
            return max(1.0, round(float(qty) * float(mat["kg_per_unit"]), 2))
    except Exception:  # noqa: BLE001
        pass
    per = float(policy.get("kg_per_unit") or 0.4)
    return max(1.0, round(float(qty) * per, 2))


def _volume_and_meta(rfq_payload: dict[str, Any], qty: float) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    try:
        from commerce.seat_catalog import material_by_code
        from agents.supplier_common.catalog_price import normalize_sku

        code = normalize_sku(
            str(
                rfq_payload.get("sku")
                or (rfq_payload.get("specifications") or {}).get("sku")
                or (rfq_payload.get("specifications") or {}).get("material_code")
                or rfq_payload.get("product_name")
                or ""
            )
        )
        if code:
            meta["material_code"] = code
            meta["sku"] = code
            mat = material_by_code(code)
            if mat:
                meta["volume_m3"] = round(float(mat.get("volume_m3") or 0) * float(qty), 4)
                meta["charge_class"] = mat.get("charge_class")
                meta["product_name"] = mat.get("name")
    except Exception:  # noqa: BLE001
        pass
    if rfq_payload.get("service_level"):
        meta["service_level"] = rfq_payload["service_level"]
    elif rfq_payload.get("urgency") in ("urgent", "express"):
        meta["service_level"] = "express"
    meta["quantity"] = qty
    return meta


async def attach_freight(
    quote_payload: dict[str, Any],
    *,
    rfq_payload: dict[str, Any],
    state: AgentState,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """在初轮/议价报价上合入运费；失败时保留货价并标注 freight 缺失原因。"""
    if not _want_freight(rfq_payload):
        quote_payload.setdefault("freight_note", "采购未要求合入运费")
        return quote_payload

    qty = float(
        (quote_payload.get("product") or {}).get("quantity")
        or rfq_payload.get("quantity")
        or 1
    )
    postal, dest_city = _dest_info(rfq_payload, policy)
    weight = _weight_kg(rfq_payload, policy, qty)
    ship_meta = _volume_and_meta(rfq_payload, qty)
    biz = str(state.get("business_id") or rfq_payload.get("purchase_request_id") or uuid4().hex[:8])
    agent_id = str(state.get("agent_id") or "supplier")
    origin_city = _origin_city(policy, agent_id)
    leader_aic = str(state.get("aic") or os.getenv("SUPPLIER_A_AIC") or "supplier-local-aic")

    discovered = await discover_logistics(
        query=str(policy.get("logistics_query") or "物流 运费报价 agentlink.logistics"),
        limit=3,
    )
    cands = discovered.get("candidates") or []
    peer = cands[0] if cands else None
    # 跨云出站：本域配置的物流 URL 优先（避免平台 ACS 域名证书链问题）
    configured_url = (os.getenv("LOGISTICS_RPC_URL") or "").strip()
    configured_aic = (os.getenv("LOGISTICS_AIC") or "").strip()
    if peer and configured_url:
        peer = {**peer, "endpoint": configured_url}
        if configured_aic:
            peer["aic"] = configured_aic
        peer["source"] = f"{peer.get('source') or 'adp'}+configured_url"
    if not peer or not peer.get("endpoint") or not peer.get("aic"):
        quote_payload["shipping_cost"] = None
        quote_payload["freight_amount"] = None
        quote_payload["freight"] = {
            "amount": 0,
            "currency": "CNY",
            "note": "未发现可用物流智能体",
            "source": discovered.get("source"),
        }
        quote_payload["freight_note"] = "discover.logistics 未命中"
        quote_payload["logistics_meta"] = {
            "source": discovered.get("source"),
            "platform_error": discovered.get("platform_error"),
            "degrade": discovered.get("degrade"),
        }
        return quote_payload

    dest_body: dict[str, Any] = {"postal_code": postal}
    if dest_city:
        dest_body["city"] = dest_city
    ship_payload: dict[str, Any] = {
        "weight_kg": weight,
        "destination": dest_body,
        "origin": {"city": origin_city},
        "origin_hint": origin_city,
        "requester_agent_id": agent_id,
        # 标明询运发起方（采购联系物流时 agent_id 为 buyer-*）
        "initiated_by": agent_id,
        **ship_meta,
    }
    envelope = wrap_business(
        "agentlink.shipping_request",
        biz,
        ship_payload,
    )
    try:
        out = await aip_start_structured(
            partner_url=str(peer["endpoint"]),
            leader_aic=leader_aic,
            partner_aic=str(peer["aic"]),
            session_id=f"sup-ship-{agent_id}-{biz}-{uuid4().hex[:6]}",
            envelope=envelope,
            local_agent_id=agent_id,
        )
    except Exception as exc:  # noqa: BLE001
        quote_payload["shipping_cost"] = None
        quote_payload["freight_amount"] = None
        quote_payload["freight"] = {"amount": 0, "currency": "CNY", "note": f"物流询价失败: {exc}"}
        quote_payload["freight_note"] = str(exc)
        quote_payload["logistics_meta"] = {
            "peer_aic": peer.get("aic"),
            "source": peer.get("source") or discovered.get("source"),
            "error": str(exc),
        }
        return quote_payload

    env = out.get("envelope") if isinstance(out.get("envelope"), dict) else {}
    pay = env.get("payload") if isinstance(env.get("payload"), dict) else {}
    cost = pay.get("shipping_cost")
    try:
        amount = float(cost) if cost is not None else 0.0
    except (TypeError, ValueError):
        amount = 0.0
    eta = pay.get("eta_days")
    distance = pay.get("distance_km")
    # 物流回执未必带 distance；用 zone 提示
    note_parts = [
        f"物流 {peer.get('name') or peer.get('agent_id') or 'partner'}",
        f"邮编{postal}",
        f"{weight}kg",
    ]
    if eta is not None:
        note_parts.append(f"ETA {eta}天")
    freight = {
        "amount": amount,
        "currency": str(pay.get("currency") or "CNY"),
        "eta_days": eta,
        "distance_km": distance,
        "shipping_quote_id": pay.get("shipping_quote_id"),
        "zone": pay.get("zone"),
        "origin_city": pay.get("origin_city") or origin_city,
        "dest_city": pay.get("dest_city") or dest_city,
        "note": " · ".join(note_parts),
        "source": peer.get("source") or discovered.get("source"),
    }
    quote_payload["shipping_cost"] = amount
    quote_payload["freight_amount"] = amount
    quote_payload["freight"] = freight
    quote_payload["freight_note"] = freight["note"]
    if distance is not None:
        quote_payload["distance_km"] = distance
    quote_payload["logistics_meta"] = {
        "peer_aic": peer.get("aic"),
        "peer_endpoint": peer.get("endpoint"),
        "source": peer.get("source") or discovered.get("source"),
        "degrade": bool(peer.get("degrade") or discovered.get("degrade")),
        "task_id": out.get("task_id"),
        "aip_state": out.get("state"),
    }
    # 条件里去掉「需确认运输」类占位
    cond = list(quote_payload.get("conditions") or [])
    quote_payload["conditions"] = [c for c in cond if "运输" not in str(c)]
    return quote_payload
