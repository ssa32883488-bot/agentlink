#!/usr/bin/env python
"""全量本地协议验证：6 Agent AIP 闭环。

端口约定：
  buyer_a 8010 | supplier_a 8011 | buyer_b 8012
  supplier_b 8013 | supplier_c 8014 | logistics 8015
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BUYER_A = os.getenv("BUYER_A_URL", "http://127.0.0.1:8010")
BUYER_B = os.getenv("BUYER_B_URL", "http://127.0.0.1:8012")
SUPPLIERS = {
    "a": ("http://127.0.0.1:8011/rpc", "supplier-a-local-aic"),
    "b": ("http://127.0.0.1:8013/rpc", "supplier-b-local-aic"),
    "c": ("http://127.0.0.1:8014/rpc", "supplier-c-local-aic"),
}
LOGISTICS = ("http://127.0.0.1:8015/rpc", "logistics-local-aic")


def _pp(label: str, obj: object) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


async def _health(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url)
    r.raise_for_status()
    return r.json()


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1) 全员健康检查
        for name, url in [
            ("buyer_a", f"{BUYER_A}/health"),
            ("buyer_b", f"{BUYER_B}/health"),
            ("supplier_a", "http://127.0.0.1:8011/health"),
            ("supplier_b", "http://127.0.0.1:8013/health"),
            ("supplier_c", "http://127.0.0.1:8014/health"),
            ("logistics", "http://127.0.0.1:8015/health"),
        ]:
            h = await _health(client, url)
            assert h["status"] == "ok", name
            print(f"health {name}: {h['agent_id']}")

        # 2) 采购 A：多供应商 RFQ（A 标准 / B 定制缺规格→澄清 / C 紧张库存）
        pr = await client.post(
            f"{BUYER_A}/api/purchases",
            json={
                "product_name": "重型脚轮",
                "quantity": 500,
                "approve": True,
                "max_total_cost": 30000,
            },
        )
        pr.raise_for_status()
        business_id = pr.json()["business_id"]
        print("buyer_a business:", business_id)

        # 2a 供应商 A — 应出报价
        ra = await client.post(
            f"{BUYER_A}/api/purchases/{business_id}/rfq",
            json={
                "business_id": business_id,
                "partner_url": SUPPLIERS["a"][0],
                "supplier_aic": SUPPLIERS["a"][1],
            },
        )
        ra.raise_for_status()
        assert ra.json().get("quote"), "supplier A must quote"
        assert ra.json()["quote"]["schema_type"] == "agentlink.initial_quote"
        print("supplier_a quote OK", ra.json()["quote"]["payload"]["unit_price"])

        # 2b 供应商 B — 标准 RFQ 缺定制字段 → awaiting-input / 无 quote
        rb = await client.post(
            f"{BUYER_A}/api/purchases/{business_id}/rfq",
            json={
                "business_id": business_id,
                "partner_url": SUPPLIERS["b"][0],
                "supplier_aic": SUPPLIERS["b"][1],
            },
        )
        # Gateway 可能仍 200 但 quote=null + state awaiting-input
        rb.raise_for_status()
        body_b = rb.json()
        assert body_b.get("quote") is None, "supplier B should clarify without custom specs"
        assert "awaiting" in str(body_b.get("state", "")).lower(), body_b
        print("supplier_b clarify OK state=", body_b.get("state"))

        # 2c 供应商 B — 带定制规格应报价
        # 直接通过 buyer 无法改 PR 规格；用独立 AIP 客户端测定制路径
        from agentlink_runtime.aip_client_util import aip_start_structured
        from agentlink_runtime.aip_payload import wrap_business

        custom_env = wrap_business(
            "agentlink.quote_request",
            f"{business_id}-custom",
            {
                "purchase_request_id": "pr-custom-1",
                "version": 1,
                "product_name": "定制脚轮",
                "specifications": {
                    "rated_load_kg_min": 300,
                    "material": "nylon",
                    "color": "black",
                },
                "quantity": 200,
                "currency": "CNY",
                "tax_included_required": True,
                "quote_deadline": "2099-01-01T00:00:00Z",
            },
        )
        custom = await aip_start_structured(
            partner_url=SUPPLIERS["b"][0],
            leader_aic="buyer-a-local-aic",
            partner_aic=SUPPLIERS["b"][1],
            session_id=f"rfq-custom-{business_id}",
            envelope=custom_env,
        )
        assert custom.get("envelope"), custom
        assert custom["envelope"]["payload"]["moq"] == 200
        print("supplier_b custom quote OK", custom["envelope"]["payload"]["unit_price"])

        # 2d 供应商 C — 500 > 库存 120 → 应有 alternatives 或 split
        rc = await client.post(
            f"{BUYER_A}/api/purchases/{business_id}/rfq",
            json={
                "business_id": business_id,
                "partner_url": SUPPLIERS["c"][0],
                "supplier_aic": SUPPLIERS["c"][1],
            },
        )
        rc.raise_for_status()
        qc = rc.json().get("quote")
        assert qc, "supplier C should still return structured options"
        payload_c = qc["payload"]
        assert payload_c.get("can_fulfill_full") is False
        assert payload_c.get("alternatives") or payload_c.get("split_fulfillment_plan")
        print(
            "supplier_c scarce OK alts=",
            len(payload_c.get("alternatives") or []),
            "split=",
            bool(payload_c.get("split_fulfillment_plan")),
        )

        # 3) 物流合入
        ship = await client.post(
            f"{BUYER_A}/api/purchases/{business_id}/shipping",
            json={
                "business_id": business_id,
                "partner_url": LOGISTICS[0],
                "logistics_aic": LOGISTICS[1],
                "weight_kg": 250,
                "postal_code": "310000",
                "zone": "domestic",
            },
        )
        ship.raise_for_status()
        sq = ship.json().get("shipping_quote")
        assert sq and sq["schema_type"] == "agentlink.shipping_quote"
        assert sq["payload"]["shipping_cost"] > 0
        print("logistics quote OK", sq["payload"]["shipping_cost"])

        # 缺邮编应澄清
        bad = await aip_start_structured(
            partner_url=LOGISTICS[0],
            leader_aic="buyer-a-local-aic",
            partner_aic=LOGISTICS[1],
            session_id="ship-bad",
            envelope=wrap_business(
                "agentlink.shipping_request",
                "biz-bad",
                {"weight_kg": 10, "zone": "local", "destination": {}},
            ),
        )
        assert bad.get("envelope") is None
        assert "awaiting" in str(bad.get("state")).lower() or bad.get("state")
        print("logistics missing postal clarify OK", bad.get("state"))

        cmp_ = await client.get(f"{BUYER_A}/api/purchases/{business_id}/comparison")
        cmp_.raise_for_status()
        _pp("comparison+TCO", cmp_.json())

        draft = await client.post(f"{BUYER_A}/api/purchases/{business_id}/order-draft")
        draft.raise_for_status()
        assert draft.json()["schema_type"] == "agentlink.order_draft"

        act = await client.post(f"{BUYER_A}/api/purchases/{business_id}/activate")
        assert act.status_code == 400
        print("activate blocked OK")

        # 4) 采购 B 快速复购（白名单供应商 A）
        prb = await client.post(
            f"{BUYER_B}/api/purchases",
            json={"product_name": "重型脚轮", "quantity": 50, "max_total_cost": 4000, "approve": True},
        )
        prb.raise_for_status()
        bid_b = prb.json()["business_id"]
        rfqb = await client.post(
            f"{BUYER_B}/api/purchases/{bid_b}/rfq",
            json={
                "business_id": bid_b,
                "partner_url": SUPPLIERS["a"][0],
                "supplier_aic": SUPPLIERS["a"][1],
            },
        )
        rfqb.raise_for_status()
        assert rfqb.json().get("quote")
        print("buyer_b quick reorder OK")

        # 超限额应拒
        over = await client.post(
            f"{BUYER_B}/api/purchases",
            json={"product_name": "重型脚轮", "quantity": 50, "max_total_cost": 99999, "approve": True},
        )
        assert over.status_code == 400
        print("buyer_b over-limit blocked OK")

        # 非白名单应拒
        bad_wl = await client.post(
            f"{BUYER_B}/api/purchases/{bid_b}/rfq",
            json={
                "business_id": bid_b,
                "partner_url": SUPPLIERS["c"][0],
                "supplier_aic": SUPPLIERS["c"][1],
            },
        )
        assert bad_wl.status_code == 400
        print("buyer_b whitelist blocked OK")

    print("\nSMOKE_ALL_OK")


if __name__ == "__main__":
    asyncio.run(main())
