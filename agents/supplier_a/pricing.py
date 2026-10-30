from __future__ import annotations

from typing import Any

from agents.supplier_common.catalog_price import quote_from_catalog
from agents.supplier_common.promo import apply_line_qty_unit_price


def compute_quote(
    policy: dict[str, Any],
    quantity: int,
    *,
    product_name: str | None = None,
    sku: str | None = None,
    specifications: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """目录价；单品满量折扣由 settle_quote_economics / enrich 统一套用，避免重复打折。"""
    priced = quote_from_catalog(
        policy,
        quantity,
        product_name=product_name,
        sku=sku,
        specifications=specifications,
    )
    if not priced.get("catalog_hit"):
        return priced
    list_unit = float(priced["unit_price"])
    # 价目层只回挂牌价；满量折扣留给议价 settle / PromoEngine 披露，避免初询泄优惠
    _, line_meta = apply_line_qty_unit_price(
        policy,
        sku=str(priced.get("sku") or ""),
        qty=int(quantity),
        unit_price=list_unit,
    )
    priced["list_unit_price"] = list_unit
    priced["unit_price"] = list_unit
    priced["_line_qty_eligible"] = line_meta
    return priced
