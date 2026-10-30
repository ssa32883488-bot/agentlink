# -*- coding: utf-8 -*-
"""本地冒烟：满量折扣/满减/跨省补贴结算 + 多方案（预算非必填）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml

from agents.supplier_common.promo import (
    build_bargain_narrative,
    goodwill_unit_price,
    settle_quote_economics,
)
from commerce.scheme_planner import plan_procurement_schemes


def load_pol(name: str) -> dict:
    return yaml.safe_load((ROOT / "agents" / name / "policy.yaml").read_text(encoding="utf-8"))


def main() -> int:
    pols = {
        "supplier-a": load_pol("supplier_a"),
        "supplier-b": load_pol("supplier_b"),
        "supplier-c": load_pol("supplier_c"),
    }
    # 中等量：A 可凑脚轮满500；B 货价可能已触满减
    mid_qty = 220
    quotes_mid = []
    for sid, unit, freight, sku in (
        ("supplier-a", 20.0, 280.0, "RM-CASTER-300"),
        ("supplier-b", 35.0, 360.0, "RM-FABRIC-PRO"),
        ("supplier-c", 100.0, 420.0, "RM-TUBE-STEEL"),
    ):
        price = goodwill_unit_price(pols[sid], previous_unit=unit, quantity=mid_qty)
        q_use = min(mid_qty, int(pols[sid].get("available_quantity") or mid_qty))
        econ = settle_quote_economics(
            pols[sid],
            qty=q_use,
            unit_price=price,
            freight=freight,
            rfq_payload={"dest_province": "河北", "destination": {"province": "河北"}, "product_name": sku},
            sku=sku,
        )
        narr = build_bargain_narrative(pols[sid], economics=econ, goal_text="优化综合成本，看看活动")
        assert narr["negotiation_style"] == "threshold_trade_not_pure_cut"
        assert econ.get("policy_hints"), sid
        print(
            "PROMO",
            sid,
            "sku",
            sku,
            "qty",
            q_use,
            "unit",
            price,
            "line_save",
            econ.get("line_qty_save"),
            "full_save",
            econ.get("full_reduction_save"),
            "next",
            (econ.get("next_tier") or {}).get("target_qty"),
            flush=True,
        )
        quotes_mid.append(
            {
                "payload": {
                    "supplier_agent_id": sid,
                    "unit_price": price,
                    "shipping_cost": freight,
                    "product": {"quantity": mid_qty, "sku": sku},
                    "policy_hints": econ.get("policy_hints"),
                }
            }
        )

    pack_mid = plan_procurement_schemes(quotes=quotes_mid, base_qty=mid_qty, dest_province="河北")
    schemes_mid = pack_mid.get("schemes") or []
    kinds_mid = {s["kind"] for s in schemes_mid}
    print("SCHEMES_MID", len(schemes_mid), "kinds", sorted(kinds_mid), flush=True)

    # 大量：C 库存不足 → 拆单
    big_qty = 500
    quotes_big = [
        {
            "payload": {
                "supplier_agent_id": sid,
                "unit_price": 20.0 if sid == "supplier-a" else (35.0 if sid == "supplier-b" else 100.0),
                "shipping_cost": 300.0,
                "product": {"quantity": big_qty},
            }
        }
        for sid in ("supplier-a", "supplier-b", "supplier-c")
    ]
    pack_big = plan_procurement_schemes(
        quotes=quotes_big, base_qty=big_qty, dest_province="河北", budget_posture="tight"
    )
    kinds_big = {s["kind"] for s in (pack_big.get("schemes") or [])}
    print("SCHEMES_BIG", len(pack_big.get("schemes") or []), "kinds", sorted(kinds_big), "rec", pack_big.get("recommended_scheme_id"), flush=True)

    # 山西补贴：qty=150 跨省应可申请（uncertain）
    econ_c = settle_quote_economics(
        pols["supplier-c"],
        qty=150,
        unit_price=100.0,
        freight=500.0,
        rfq_payload={"dest_province": "河北"},
        sku="RM-TUBE-STEEL",
    )
    sub = econ_c["cross_province_subsidy"]
    print("SUBSIDY applied", sub.get("applied"), "uncertain", sub.get("uncertain"), "amt", sub.get("subsidy_amount"), flush=True)

    # 脚轮满500应九折
    econ_a500 = settle_quote_economics(
        pols["supplier-a"],
        qty=500,
        unit_price=20.0,
        freight=200.0,
        rfq_payload={"dest_province": "河北"},
        sku="RM-CASTER-300",
    )
    print(
        "CASTER500 unit",
        econ_a500.get("unit_price"),
        "line_save",
        econ_a500.get("line_qty_save"),
        flush=True,
    )

    pack_ample = plan_procurement_schemes(
        quotes=quotes_mid, base_qty=mid_qty, dest_province="河北", budget_posture="ample"
    )
    rec_ample = (pack_ample.get("schemes") or [{}])[0]

    ok = (
        pack_mid.get("budget_required") is False
        and "single_as_is" in kinds_mid
        and "single_reach_promo" in kinds_mid
        and "split_order" in kinds_big
        and bool(sub.get("applied"))
        and bool(sub.get("uncertain"))
        and abs(float(econ_a500.get("unit_price") or 0) - 18.0) < 0.01
        and float(econ_a500.get("line_qty_save") or 0) > 0
        and rec_ample.get("kind") in ("single_reach_promo", "single_as_is")
    )
    for sid, sku in (
        ("supplier-a", "RM-CASTER-300"),
        ("supplier-b", "RM-FABRIC-PRO"),
        ("supplier-c", "RM-TUBE-STEEL"),
    ):
        hints = settle_quote_economics(
            pols[sid],
            qty=200,
            unit_price=40.0,
            freight=200.0,
            rfq_payload={"dest_province": "河北"},
            sku=sku,
        ).get("policy_hints") or []
        if not any("满" in h for h in hints):
            print("FAIL missing 满 hint", sid, hints)
            ok = False

    out = {
        "ok": ok,
        "mid_kinds": sorted(kinds_mid),
        "big_kinds": sorted(kinds_big),
        "ample_top": rec_ample.get("scheme_id"),
        "subsidy_applied": sub.get("applied"),
        "caster_unit_500": econ_a500.get("unit_price"),
        "budget_required": False,
    }
    print("SUMMARY", json.dumps(out, ensure_ascii=False), flush=True)
    print("PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
