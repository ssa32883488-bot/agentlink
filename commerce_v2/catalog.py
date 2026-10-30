# -*- coding: utf-8 -*-
"""供应/物流主数据（只读智力底座）。"""
from __future__ import annotations

from typing import Any

SUPPLIERS: dict[str, dict[str, Any]] = {
    "supplier-a": {
        "title": "沧州组件厂·供应A",
        "city": "沧州",
        "blurb": "五金结构件 · 脚轮满500九折",
        "skus": {
            "RM-CASTER-300": {
                "name": "重型脚轮300kg",
                "list_price": 20.0,
                "spec": {"rated_load_kg": 300, "material": "尼龙+轴承", "unit": "只"},
                "lead_days": 5,
                "on_hand": 2000,
                "promo": {"type": "qty_discount", "min_qty": 500, "rate": 0.9, "reason": "脚轮满500件九折"},
            },
            "RM-CASTER-200": {
                "name": "标准脚轮200kg",
                "list_price": 15.0,
                "spec": {"rated_load_kg": 200, "material": "尼龙", "unit": "只"},
                "lead_days": 4,
                "on_hand": 2500,
                "promo": {"type": "qty_discount", "min_qty": 500, "rate": 0.9, "reason": "脚轮满500件九折"},
            },
        },
    },
    "supplier-b": {
        "title": "邢台软装厂·供应B",
        "city": "邢台",
        "blurb": "面料/海绵坐垫 · MOQ 定制",
        "skus": {
            "RM-FABRIC-PRO": {
                "name": "高档座椅面料",
                "list_price": 35.0,
                "spec": {"material": "织物", "color": "黑", "unit": "套", "moq": 50},
                "lead_days": 7,
                "on_hand": 1500,
                "promo": {"type": "amount_off", "min_amount": 10000, "off": 1000, "reason": "货价满1万减1000"},
            },
            "RM-FABRIC-STD": {
                "name": "标准座椅面料",
                "list_price": 12.0,
                "spec": {"material": "织物", "unit": "套", "moq": 50},
                "lead_days": 6,
                "on_hand": 3000,
                "promo": None,
            },
            "RM-FOAM-MEM": {
                "name": "记忆海绵坐垫",
                "list_price": 55.0,
                "spec": {"material": "记忆海绵", "unit": "块", "moq": 20},
                "lead_days": 10,
                "on_hand": 800,
                "promo": None,
            },
            "RM-FOAM-STD": {
                "name": "普通海绵坐垫",
                "list_price": 20.0,
                "spec": {"material": "普通海绵", "unit": "块", "moq": 20},
                "lead_days": 8,
                "on_hand": 1200,
                "promo": None,
            },
        },
    },
    "supplier-c": {
        "title": "太原组件厂·供应C",
        "city": "太原",
        "blurb": "结构件/替代/坐垫 · 紧缺可分批",
        "skus": {
            "RM-CASTER-200": {
                "name": "标准脚轮200kg",
                "list_price": 15.0,
                "spec": {"rated_load_kg": 200, "material": "PP", "unit": "只"},
                "lead_days": 8,
                "on_hand": 800,
                "promo": {"type": "none"},
            },
            "RM-CASTER-300": {
                "name": "重型脚轮300kg（紧缺）",
                "list_price": 22.0,
                "spec": {"rated_load_kg": 300, "material": "尼龙", "unit": "只", "scarce": True},
                "lead_days": 12,
                "on_hand": 120,
                "promo": {"type": "none"},
            },
            "RM-FOAM-MEM": {
                "name": "记忆海绵坐垫",
                "list_price": 50.0,
                "spec": {"material": "记忆海绵", "unit": "块", "scarce": True},
                "lead_days": 7,
                "on_hand": 150,
                "promo": {"type": "none"},
            },
            "RM-FOAM-STD": {
                "name": "普通海绵坐垫",
                "list_price": 20.0,
                "spec": {"material": "普通海绵", "unit": "块"},
                "lead_days": 6,
                "on_hand": 200,
                "promo": {"type": "none"},
            },
        },
    },
}

LOGISTICS_REQUIRED = [
    {"key": "goods_spec", "label": "货物规格摘要", "holder": "supplier_or_order"},
    {"key": "chargeable_qty", "label": "计费相关量（件数/重量/体积口径）", "holder": "order"},
    {"key": "origin", "label": "起运地", "holder": "supplier"},
    {"key": "destination", "label": "到达地", "holder": "buyer"},
    {"key": "ship_date", "label": "期望出库/发货时间", "holder": "supplier"},
]

BUYER_PROFILES = {
    "buyer-a": {
        "title": "保定高端座椅",
        "default_sku": "RM-CASTER-300",
        "default_name": "重型脚轮300kg",
        "destination": "保定",
        "rewrite_hint": "高端座椅产线场景；仅当用户未点名品类时可参考，不得覆盖用户已说的物料",
    },
    "buyer-b": {
        "title": "承德平价办公",
        "default_sku": "RM-CASTER-200",
        "default_name": "标准脚轮200kg",
        "destination": "承德",
        "rewrite_hint": "平价办公产线场景；仅当用户未点名品类时可参考，不得覆盖用户已说的物料",
    },
}


def local_candidates_for_sku(sku: str) -> list[dict[str, Any]]:
    out = []
    for aid, meta in SUPPLIERS.items():
        if sku in meta["skus"]:
            out.append(
                {
                    "agent_id": aid,
                    "candidate_id": aid,
                    "title": meta["title"],
                    "city": meta["city"],
                    "blurb": meta["blurb"],
                    "endpoint": _rpc(aid),
                }
            )
    return out


def _rpc(aid: str) -> str:
    import os

    env = {
        "buyer-a": ("BUYER_A_RPC_URL", "http://127.0.0.1:8010/rpc"),
        "buyer-b": ("BUYER_B_RPC_URL", "http://127.0.0.1:8012/rpc"),
        "supplier-a": ("SUPPLIER_A_RPC_URL", "http://127.0.0.1:8011/rpc"),
        "supplier-b": ("SUPPLIER_B_RPC_URL", "http://127.0.0.1:8013/rpc"),
        "supplier-c": ("SUPPLIER_C_RPC_URL", "http://127.0.0.1:8014/rpc"),
        "logistics": ("LOGISTICS_RPC_URL", "http://127.0.0.1:8015/rpc"),
    }
    k, d = env.get(aid, ("", ""))
    return os.getenv(k, d) if k else d
