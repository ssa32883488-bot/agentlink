# -*- coding: utf-8 -*-
"""供应商 Partner 工具目录。下单工具仅在采购携带 place_order=on 时生效。"""
from __future__ import annotations

from typing import Any


def is_place_order_on(value: Any) -> bool:
    """place_order=on：用户已明确确认购买 / 决断下单。"""
    if value is True:
        return True
    s = str(value or "").strip().lower()
    return s in ("on", "1", "true", "yes", "y")


def tool_catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": "place_order",
            "schema_type": "v2.place_order",
            "title": "接收采购下单",
            "description": (
                "采购方在用户明确下单后调用。必须携带 place_order=on；"
                "供应侧写入待确认货单，买卖双方 Gate 确认后生效。"
            ),
            "required": ["place_order", "order"],
            "parameters": {
                "place_order": {
                    "type": "string",
                    "enum": ["on", "off"],
                    "description": "仅当用户明确下单时为 on；询价/议价阶段必须为 off 或不传",
                },
                "order": {
                    "type": "object",
                    "description": "共享货单草案（order_id/sku/qty/单价等）",
                },
            },
            "gate": "bilateral_ack",
        },
        {
            "name": "initial_quote",
            "schema_type": "v2.initial_quote",
            "title": "初报",
            "description": "按挂牌价报价，不落单",
        },
        {
            "name": "promo_query",
            "schema_type": "v2.promo_query",
            "title": "优惠政策查询",
            "description": "公示优惠，不落单",
        },
        {
            "name": "bargain",
            "schema_type": "v2.bargain",
            "title": "议价/成交核算",
            "description": "按真实数量套用优惠核算，不落单",
        },
        {
            "name": "spec_query",
            "schema_type": "v2.spec_query",
            "title": "规格/起运查询",
            "description": "物流合入前查规格，不落单",
        },
    ]
