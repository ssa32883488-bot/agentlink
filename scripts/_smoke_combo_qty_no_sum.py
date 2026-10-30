# -*- coding: utf-8 -*-
"""组合需求：下单数量不得把多行 qty 加总。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from agents.buyer_a.graph import build_order_draft, _resolve_draft_line  # noqa: E402
from commerce.flow_service import create_from_brief, _narrow_brief_for_order  # noqa: E402


def main() -> None:
    case = create_from_brief(
        product_name="重型脚轮+高档面料",
        quantity=500,
        lines=[
            {"sku": "RM-CASTER-300", "name": "重型脚轮300kg", "qty": 500},
            {"sku": "RM-FABRIC-PRO", "name": "高档座椅面料", "qty": 200},
        ],
    )
    brief = case["brief"]
    assert brief.get("combo") is True
    assert int(brief["quantity"]) == 500, brief["quantity"]  # 首行，不是 700
    assert abs(sum(float(x["qty"]) for x in brief["lines"]) - 700) < 1e-6

    narrow = _narrow_brief_for_order(brief, sku="RM-CASTER-300")
    assert int(narrow["quantity"]) == 500, narrow
    assert "面料" not in str(narrow.get("product_name") or "")

    quote = {
        "payload": {
            "supplier_agent_id": "supplier-a",
            "sku": "RM-CASTER-300",
            "product_name": "重型脚轮300kg",
            "unit_price": 18,
            "quantity": 500,
            "product": {"sku": "RM-CASTER-300", "quantity": 500},
            "goods_total": 9000,
        }
    }
    # 即使误把 brief.quantity 写成 700，也应按行收成 500
    poisoned = dict(brief)
    poisoned["quantity"] = 700
    draft = build_order_draft(
        business_id=case["case_id"],
        purchase_request=_narrow_brief_for_order(poisoned, sku="RM-CASTER-300", quote_payload=quote["payload"]),
        selected_quote=quote,
    )["payload"]
    assert int(draft["quantity"]) == 500, draft
    assert float(draft["goods_total"]) == 9000.0, draft
    assert draft.get("sku") == "RM-CASTER-300"

    # 无收窄、仅报价：combo brief 也不准吃 700
    qty, name, sku = _resolve_draft_line(poisoned, quote["payload"])
    assert qty == 500, (qty, name, sku)

    print("PASS_COMBO_QTY", draft["quantity"], draft["goods_total"], flush=True)


if __name__ == "__main__":
    main()
