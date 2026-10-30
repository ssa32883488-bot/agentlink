from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from agentlink_runtime.aip_payload import wrap_business
from agentlink_runtime.graph_base import AgentState
from commerce.merchant import resolve_lane
from commerce.seat_catalog import chargeable_weight_kg, material_by_code, route_factor


def _origin_city(payload: dict[str, Any]) -> str | None:
    origin = payload.get("origin") if isinstance(payload.get("origin"), dict) else {}
    hint = payload.get("origin_hint")
    city = origin.get("city") or hint
    return str(city).strip() if city else None


def _dest_city(payload: dict[str, Any], postal: str | None) -> str | None:
    from commerce.merchant import city_for_postal

    dest = payload.get("destination") if isinstance(payload.get("destination"), dict) else {}
    if dest.get("city"):
        return str(dest["city"]).strip()
    return city_for_postal(postal)


def _pick_service(policy: dict[str, Any], payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """未指定服务档时默认 economy（最经济单方案，减流程）。"""
    services = policy.get("services") if isinstance(policy.get("services"), dict) else {}
    explicit = payload.get("service_level") or payload.get("service")
    key = str(
        explicit or policy.get("default_service") or "economy"
    ).strip().lower()
    # urgency 仅在调用方未点名服务档时作为弱提示；仍优先最经济，除非明确 urgent/express
    if not explicit:
        urg = str(payload.get("urgency") or "").strip().lower()
        if urg in ("urgent", "express", "asap"):
            key = "express"
        else:
            key = str(policy.get("default_service") or "economy").strip().lower()
    if key not in services and services:
        key = str(policy.get("default_service") or "economy")
        if key not in services:
            key = "economy" if "economy" in services else next(iter(services))
    svc = services.get(key) if isinstance(services.get(key), dict) else {}
    if not svc:
        # 兼容旧扁平费率
        return "legacy", {
            "label": "经济",
            "eta_days_min": int(policy.get("eta_days_base", 5)),
            "eta_days_max": int(policy.get("eta_days_base", 5)) + 2,
            "base_fee": float(policy.get("min_charge", 80)),
            "base_kg": 100,
            "base_m3": 1.0,
            "per_kg": float(policy.get("base_rate_per_kg", 0.4)),
            "per_m3": 80.0,
        }
    return key, svc


def _volume_m3(payload: dict[str, Any], qty: float) -> float:
    if payload.get("volume_m3") is not None:
        try:
            return max(0.0, float(payload["volume_m3"]))
        except (TypeError, ValueError):
            pass
    code = str(payload.get("material_code") or payload.get("sku") or "").upper()
    mat = material_by_code(code) if code else None
    if mat and mat.get("volume_m3") is not None:
        return float(mat["volume_m3"]) * max(qty, 1.0)
    # 缺省：按重量粗估体积（重货 ~0.001 m³/kg）
    try:
        w = float(payload.get("weight_kg") or 0)
    except (TypeError, ValueError):
        w = 0.0
    return round(max(w, 1.0) * 0.001, 4)


def _charge_class(payload: dict[str, Any]) -> str:
    explicit = payload.get("charge_class")
    if explicit in ("heavy", "bulky"):
        return str(explicit)
    code = str(payload.get("material_code") or payload.get("sku") or "").upper()
    mat = material_by_code(code) if code else None
    if mat:
        return str(mat.get("charge_class") or "heavy")
    # 面料/海绵关键词
    name = str(payload.get("product_name") or "")
    if any(k in name for k in ("面料", "海绵", "foam", "fabric")):
        return "bulky"
    return "heavy"


def _quote_cost(
    *,
    svc: dict[str, Any],
    charge_kg: float,
    volume_m3: float,
    route_mult: float,
) -> dict[str, Any]:
    base_fee = float(svc.get("base_fee", 80))
    base_kg = float(svc.get("base_kg", 100))
    base_m3 = float(svc.get("base_m3", 1.0))
    per_kg = float(svc.get("per_kg", 0.8))
    per_m3 = float(svc.get("per_m3", 150))

    over_kg = max(0.0, charge_kg - base_kg)
    over_m3 = max(0.0, volume_m3 - base_m3)
    # 续费：重量续费与体积续费取大（与计费重逻辑一致）
    cont = max(over_kg * per_kg, over_m3 * per_m3)
    raw = base_fee + cont
    cost = round(raw * float(route_mult), 2)
    return {
        "base_fee": base_fee,
        "continuation": round(cont, 2),
        "route_factor": route_mult,
        "shipping_cost": cost,
        "over_kg": round(over_kg, 2),
        "over_m3": round(over_m3, 4),
    }


def run_logistics_pipeline(
    *,
    state: AgentState,
    envelope: dict[str, Any],
    policy: dict[str, Any],
) -> AgentState:
    if envelope.get("schema_type") not in (
        "agentlink.shipping_request",
        "agentlink.shipping_quote_request",
    ):
        state["outcome"] = {
            "aip_state": "rejected",
            "reason": f"unexpected schema_type={envelope.get('schema_type')}",
        }
        return state

    payload = envelope.get("payload") or {}
    dest = payload.get("destination") or {}
    postal = dest.get("postal_code") or payload.get("postal_code")
    if not postal:
        state["outcome"] = {
            "aip_state": "awaiting-input",
            "clarify": "missing destination.postal_code",
        }
        return state

    weight = payload.get("weight_kg")
    if weight is None:
        # 可从 SKU×数量推导实际重量（主数据 kg_per_unit）
        try:
            from commerce.seat_catalog import estimate_weight_kg, material_by_code
            from agents.supplier_common.catalog_price import normalize_sku

            code = normalize_sku(
                str(
                    payload.get("sku")
                    or payload.get("product_name")
                    or (payload.get("product") or {}).get("sku")
                    or ""
                )
            )
            qty = float(payload.get("quantity") or (payload.get("product") or {}).get("quantity") or 1)
            derived = estimate_weight_kg(code, qty) if code else None
            if derived is None and code:
                mat = material_by_code(code)
                if mat and mat.get("kg_per_unit") is not None:
                    derived = float(mat["kg_per_unit"]) * qty
            weight = derived
        except Exception:  # noqa: BLE001
            weight = None
    if weight is None:
        state["outcome"] = {
            "aip_state": "awaiting-input",
            "clarify": "missing weight_kg（报价未带重量且无法从 SKU 推导）",
        }
        return state
    weight = float(weight)
    max_w = float(policy.get("max_weight_kg", 20000))
    if weight <= 0 or weight > max_w:
        state["outcome"] = {
            "aip_state": "rejected",
            "reason": f"weight_kg out of range (0, {max_w}]",
        }
        return state

    origin = _origin_city(payload)
    dest_city = _dest_city(payload, str(postal))
    lane = resolve_lane(origin_city=origin, dest_postal=str(postal), dest_city=dest_city)

    zones = policy.get("zones") or {}
    if lane.get("found") and lane.get("distance_km") is not None:
        distance = float(lane["distance_km"])
        zone_name = str(lane.get("lane_key") or f"{origin}_{dest_city}")
    else:
        zone_name = str(payload.get("zone") or "domestic")
        zone = zones.get(zone_name) or zones.get("domestic") or {"multiplier": 1.2, "distance_km": 500}
        distance = float(zone.get("distance_km", 500))

    band_name, route_mult = route_factor(distance)
    # policy.route_bands 可覆盖 seat_catalog
    bands = policy.get("route_bands")
    if isinstance(bands, list) and bands:
        for band in bands:
            if not isinstance(band, dict):
                continue
            if distance <= float(band.get("max_km", 10**9)):
                band_name = str(band.get("name") or band_name)
                route_mult = float(band.get("factor") or route_mult)
                break

    qty = float(payload.get("quantity") or 1)
    volume = _volume_m3(payload, qty)
    cclass = _charge_class(payload)
    charge_kg = chargeable_weight_kg(
        actual_kg=weight, volume_m3=volume, charge_class=cclass
    )
    svc_key, svc = _pick_service(policy, payload)
    priced = _quote_cost(
        svc=svc, charge_kg=charge_kg, volume_m3=volume, route_mult=route_mult
    )
    eta_min = int(svc.get("eta_days_min", policy.get("eta_days_base", 3)))
    eta_max = int(svc.get("eta_days_max", eta_min + 1))
    # 跨大区略加天
    if route_mult >= 1.5:
        eta_min += 1
        eta_max += 1
    eta = eta_max

    quote = {
        "shipping_quote_id": f"ship-{uuid4().hex[:8]}",
        "business_id": state.get("business_id") or envelope.get("business_id"),
        "currency": policy.get("currency", "CNY"),
        "shipping_cost": priced["shipping_cost"],
        "eta_days": eta,
        "eta_days_min": eta_min,
        "eta_days_max": eta_max,
        "zone": zone_name,
        "route_band": band_name,
        "route_factor": route_mult,
        "distance_km": distance,
        "weight_kg": weight,
        "volume_m3": round(volume, 4),
        "chargeable_weight_kg": round(charge_kg, 2),
        "charge_class": cclass,
        "service_level": svc_key,
        "service_label": svc.get("label"),
        "service_hint": svc.get("hint"),
        "pricing_breakdown": {
            "base_fee": priced["base_fee"],
            "continuation": priced["continuation"],
            "route_factor": priced["route_factor"],
            "over_kg": priced["over_kg"],
            "over_m3": priced["over_m3"],
        },
        "origin_city": origin,
        "dest_city": dest_city or lane.get("dest_city"),
        "destination_postal_code": postal,
        "lane_ref": True if lane.get("found") else False,
        "valid_until": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        "carrier_hint": "采联智运·各城分公司",
    }
    state["outcome"] = {
        "aip_state": "awaiting-completion",
        "product_name": "shipping_quote",
        "envelope": wrap_business(
            "agentlink.shipping_quote",
            state.get("business_id") or envelope.get("business_id") or "",
            quote,
        ),
    }
    return state
