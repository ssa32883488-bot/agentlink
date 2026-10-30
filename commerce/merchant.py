"""商家档案与运费里程矩阵。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent
_PROFILES = _ROOT / "merchant_profiles.yaml"


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    return yaml.safe_load(_PROFILES.read_text(encoding="utf-8")) or {}


def reload() -> None:
    _raw.cache_clear()


def profile(agent_id: str) -> dict[str, Any]:
    agents = (_raw().get("agents") or {})
    p = agents.get(agent_id)
    if not isinstance(p, dict):
        return {"agent_id": agent_id, "trade_name": agent_id, "city": "", "postal_code": ""}
    return {"agent_id": agent_id, **p}


def all_profiles() -> dict[str, dict[str, Any]]:
    agents = _raw().get("agents") or {}
    return {k: {"agent_id": k, **v} for k, v in agents.items() if isinstance(v, dict)}


def city_for_postal(postal_code: str | None) -> str | None:
    if not postal_code:
        return None
    m = _raw().get("postal_to_city") or {}
    return m.get(str(postal_code).strip()) or m.get(str(postal_code).strip()[:3] + "000")


def postal_for_city(city: str | None) -> str | None:
    if not city:
        return None
    m = _raw().get("postal_to_city") or {}
    for code, c in m.items():
        if c == city:
            return str(code)
    return None


def distance_km(origin_city: str | None, dest_city: str | None) -> float | None:
    if not origin_city or not dest_city:
        return None
    lanes = _raw().get("lanes") or {}
    row = lanes.get(origin_city) or {}
    val = row.get(dest_city)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def buyer_destination(agent_id: str | None = None) -> dict[str, Any]:
    """采购方收货地（写入 RFQ / shipping_request）。"""
    import os

    aid = (agent_id or os.getenv("BUYER_AGENT_ID") or "buyer-a").strip()
    p = profile(aid)
    city = str(p.get("ship_to_city") or p.get("city") or "")
    postal = str(p.get("postal_code") or postal_for_city(city) or "071000")
    return {
        "postal_code": postal,
        "city": city,
        "address": p.get("address"),
        "trade_name": p.get("trade_name"),
        "agent_id": aid,
    }


def resolve_lane(
    *,
    origin_city: str | None,
    dest_postal: str | None = None,
    dest_city: str | None = None,
) -> dict[str, Any]:
    """按商家城市解析运费参考里程。"""
    d_city = dest_city or city_for_postal(dest_postal)
    km = distance_km(origin_city, d_city)
    return {
        "origin_city": origin_city,
        "dest_city": d_city,
        "dest_postal_code": dest_postal,
        "distance_km": km,
        "lane_key": f"{origin_city}_{d_city}" if origin_city and d_city else None,
        "found": km is not None,
    }
