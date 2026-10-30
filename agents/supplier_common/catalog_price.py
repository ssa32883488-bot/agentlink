"""按 policy.catalog / RFQ 物料码解析单价与可供量（座椅场景）。"""
from __future__ import annotations

import re
from typing import Any


_CODE_RE = re.compile(r"\b(RM-[A-Z0-9-]+)\b", re.I)


def _catalog_rows(policy: dict[str, Any]) -> list[dict[str, Any]]:
    rows = policy.get("catalog") or []
    return [r for r in rows if isinstance(r, dict) and r.get("sku")]


def normalize_sku(text: str | None) -> str | None:
    if not text:
        return None
    s = str(text).strip().upper().replace(" ", "")
    if s.startswith("RM-"):
        return s
    m = _CODE_RE.search(str(text))
    if m:
        return m.group(1).upper().replace(" ", "")
    # 别名
    aliases = {
        "重型脚轮": "RM-CASTER-300",
        "标准脚轮": "RM-CASTER-200",
        "脚轮": "RM-CASTER-300",
        "扶手": "RM-ARMREST",
        "五星脚": "RM-BASE-NYLON",
        "气压棒": "RM-GASLIFT",
        "气杆": "RM-GASLIFT",
        "椅架": "RM-TUBE-STEEL",
        "钢管": "RM-TUBE-STEEL",
        "记忆海绵坐垫": "RM-FOAM-MEM",
        "记忆海绵": "RM-FOAM-MEM",
        "普通海绵坐垫": "RM-FOAM-STD",
        "普通海绵": "RM-FOAM-STD",
        "海绵坐垫": "RM-FOAM-MEM",
        "坐垫": "RM-FOAM-MEM",
        "高档面料": "RM-FABRIC-PRO",
        "普通面料": "RM-FABRIC-STD",
        "面料": "RM-FABRIC-PRO",
    }
    for k, v in aliases.items():
        if k in str(text):
            return v
    return None


def requested_sku(
    *,
    product_name: str | None = None,
    sku: str | None = None,
    specifications: dict[str, Any] | None = None,
) -> str | None:
    specs = specifications if isinstance(specifications, dict) else {}
    return (
        normalize_sku(sku)
        or normalize_sku(str(specs.get("sku") or specs.get("material_code") or ""))
        or normalize_sku(product_name)
    )


def resolve_catalog_item(
    policy: dict[str, Any],
    *,
    product_name: str | None = None,
    sku: str | None = None,
    specifications: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """仅返回本厂目录中真正命中的行；禁止回落 default_sku / 首行。"""
    rows = _catalog_rows(policy)
    if not rows:
        return None
    want = requested_sku(product_name=product_name, sku=sku, specifications=specifications)
    if not want:
        return None
    for r in rows:
        if str(r.get("sku") or "").upper() == want:
            return r
    return None


def quote_from_catalog(
    policy: dict[str, Any],
    quantity: int,
    *,
    product_name: str | None = None,
    sku: str | None = None,
    specifications: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """优先 catalog 行价；未命中则 catalog_hit=False，禁止用默认商品冒充。"""
    want = requested_sku(product_name=product_name, sku=sku, specifications=specifications)
    item = resolve_catalog_item(
        policy,
        product_name=product_name,
        sku=sku,
        specifications=specifications,
    )
    qty = int(quantity)
    if not item:
        return {
            "requested_sku": want,
            "requested_product_name": product_name,
            "catalog_hit": False,
            "can_fulfill": False,
            "pricing_mode": "list_plus_promo_only",
            "reject_reason": (
                "无法识别请求物料，拒绝用默认商品冒充报价"
                if not want
                else f"本厂目录无此物料: {want}" + (f" ({product_name})" if product_name else "")
            ),
        }

    buffer_days = int(policy.get("buffer_days", 1))
    unit = float(item.get("unit_price") or item.get("list_price") or 0)
    avail = int(item.get("available_quantity") or policy.get("available_quantity") or 0)
    lead = int(item.get("lead_time_days") or 0)
    if lead <= 0:
        lead = int(policy.get("production_days") or policy.get("production_days_base") or 5) + buffer_days
    else:
        lead = lead + buffer_days
    moq = int(item.get("moq") or policy.get("moq") or 1)
    sku_code = str(item.get("sku"))
    name = str(item.get("name") or sku_code)

    # 已取消私下底价：兼容字段恒等于挂牌价；真实让利只走 promotions
    # 合入主数据物理规格（重量/体积/包装），供采购询运与回执核对
    try:
        from commerce.seat_catalog import product_physical_specs

        physical = product_physical_specs(sku_code, qty=qty)
    except Exception:  # noqa: BLE001
        physical = {"sku": sku_code, "name": name, "quantity": qty}

    return {
        "sku": sku_code,
        "name": name,
        "requested_sku": want,
        "unit_price": round(unit, 2),
        "list_unit_price": round(unit, 2),
        "floor_price": round(unit, 2),
        "currency": "CNY",
        "tax_included": bool(policy.get("default_tax_included", True)),
        "available_quantity": avail,
        "lead_time_days": lead,
        "moq": moq,
        "strategy_tag": policy.get("strategy_tag", "price-first"),
        "can_fulfill": avail >= qty,
        "catalog_hit": True,
        "pricing_mode": "list_plus_promo_only",
        "physical_specs": physical,
        "weight_kg": physical.get("weight_kg"),
        "volume_m3": physical.get("volume_m3"),
        "kg_per_unit": physical.get("kg_per_unit"),
        "pack_cm": physical.get("pack_cm"),
        "charge_class": physical.get("charge_class"),
        "unit": physical.get("unit") or "件",
    }
