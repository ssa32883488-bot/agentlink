# -*- coding: utf-8 -*-
"""改写前检索：采购画像 + 本厂库存物料 + 供应目录/库存。"""
from __future__ import annotations

from typing import Any

from commerce_v2.catalog import BUYER_PROFILES, SUPPLIERS


def _buyer_merchant(agent_id: str) -> dict[str, Any]:
    try:
        from commerce.merchant import profile

        return profile(agent_id) or {}
    except Exception:
        return {}


def _buyer_inventory(agent_id: str) -> list[dict[str, Any]]:
    """优先读本域 SQLite 库存；失败则用 seat_catalog 画像物料表。"""
    try:
        import os

        # buyer_service 用 AGENT 环境；临时对齐
        prev = os.environ.get("AGENT")
        os.environ["AGENT"] = agent_id
        try:
            from commerce import buyer_service as bs

            items = bs.list_inventory()
            if items:
                return [
                    {
                        "code": it.get("code"),
                        "name": it.get("name"),
                        "unit": it.get("unit"),
                        "on_hand": it.get("on_hand"),
                        "available": it.get("available"),
                        "safety_stock": it.get("safety_stock"),
                        "preferred_supplier": it.get("preferred_supplier"),
                        "low": it.get("low"),
                    }
                    for it in items
                ]
        finally:
            if prev is None:
                os.environ.pop("AGENT", None)
            else:
                os.environ["AGENT"] = prev
    except Exception:
        pass

    try:
        from commerce.seat_catalog import BUYER_A_INV, BUYER_A_MATERIALS, BUYER_B_INV, BUYER_B_MATERIALS

        mats = BUYER_A_MATERIALS if agent_id == "buyer-a" else BUYER_B_MATERIALS
        inv = BUYER_A_INV if agent_id == "buyer-a" else BUYER_B_INV
        out = []
        for code, name, unit, pref, safety in mats:
            on_hand = float(inv.get(code, 0))
            out.append(
                {
                    "code": code,
                    "name": name,
                    "unit": unit,
                    "on_hand": on_hand,
                    "available": on_hand,
                    "safety_stock": safety,
                    "preferred_supplier": pref,
                    "low": on_hand < float(safety),
                }
            )
        return out
    except Exception:
        return []


def _supplier_catalog_snapshot() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for aid, meta in SUPPLIERS.items():
        for sku, item in (meta.get("skus") or {}).items():
            rows.append(
                {
                    "supplier_id": aid,
                    "supplier_title": meta.get("title"),
                    "city": meta.get("city"),
                    "sku": sku,
                    "name": item.get("name"),
                    "list_price": item.get("list_price"),
                    "on_hand": item.get("on_hand"),
                    "unit": (item.get("spec") or {}).get("unit"),
                    "lead_days": item.get("lead_days"),
                    "promo": item.get("promo"),
                    "blurb": meta.get("blurb"),
                }
            )
    return rows


def gather_rewrite_evidence(agent_id: str) -> dict[str, Any]:
    buyer_p = BUYER_PROFILES.get(agent_id) or BUYER_PROFILES["buyer-a"]
    merchant = _buyer_merchant(agent_id)
    inventory = _buyer_inventory(agent_id)
    catalogs = _supplier_catalog_snapshot()
    return {
        "buyer_id": agent_id,
        "buyer_profile": {
            "title": buyer_p.get("title"),
            "destination": buyer_p.get("destination"),
            "rewrite_hint": buyer_p.get("rewrite_hint"),
            "trade_name": merchant.get("trade_name") or merchant.get("organization"),
            "city": merchant.get("city"),
            "notes": merchant.get("notes"),
        },
        "buyer_inventory": inventory,
        "supplier_catalog": catalogs,
        "evidence_summary": _summary(inventory, catalogs, merchant, buyer_p),
    }


def _summary(
    inventory: list[dict[str, Any]],
    catalogs: list[dict[str, Any]],
    merchant: dict[str, Any],
    buyer_p: dict[str, Any],
) -> str:
    lines = [
        f"采购画像：{merchant.get('trade_name') or buyer_p.get('title')} · "
        f"{merchant.get('city') or buyer_p.get('destination')} · {merchant.get('notes') or buyer_p.get('rewrite_hint')}",
        f"本厂物料/库存共 {len(inventory)} 项：",
    ]
    for it in inventory:
        low = "【低于安全线】" if it.get("low") else ""
        lines.append(
            f"  - {it.get('code')} {it.get('name')} · 库存{it.get('available')}{it.get('unit') or ''} "
            f"安全线{it.get('safety_stock')} · 偏好供应 {it.get('preferred_supplier')} {low}"
        )
    lines.append(f"供应目录/可售库存共 {len(catalogs)} 行：")
    for row in catalogs:
        lines.append(
            f"  - [{row.get('supplier_id')}] {row.get('sku')} {row.get('name')} · "
            f"挂牌{row.get('list_price')} · 库存{row.get('on_hand')} · 交期{row.get('lead_days')}天"
        )
    return "\n".join(lines)


def format_evidence_for_prompt(evidence: dict[str, Any]) -> str:
    return str(evidence.get("evidence_summary") or "")
