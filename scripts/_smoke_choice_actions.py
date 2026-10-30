# -*- coding: utf-8 -*-
"""冒烟：询价后应带可点选按钮；ui.offer_choices 可归一化。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commerce.choice_actions import normalize_offered_choices, post_quote_choices


def main() -> int:
    w = post_quote_choices(
        case_id="case-demo",
        lowest_agent_id="supplier-a",
        supplier_ids=["supplier-a", "supplier-b", "supplier-c"],
    )
    assert w["kind"] == "choice_actions"
    assert w["allow_note"] is True
    assert len(w["choices"]) >= 3
    assert w["ui_hint"]["form"] == "choice_actions"

    offered = normalize_offered_choices(
        case_id="case-demo",
        prompt="请点选",
        choices_json=json.dumps(
            [
                {"id": "n1", "label": "与A/C议价", "message": "请议价 A 和 C", "primary": True},
                {"id": "n2", "label": "选A下单", "message": "flow.decide_order supplier-a"},
                {"id": "n3", "label": "等补贴", "message": "澄清 supplier-c 补贴"},
            ],
            ensure_ascii=False,
        ),
    )
    assert len(offered["choices"]) == 3
    assert offered["choices"][0]["primary"] is True
    print("PASS", json.dumps({"n": len(w["choices"]), "offered": len(offered["choices"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
