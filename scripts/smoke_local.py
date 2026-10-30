#!/usr/bin/env python
"""本地冒烟：采购 A → 供应商 A：建单 → RFQ → 比较 → 草案 → 激活应被拒。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BUYER = os.getenv("BUYER_URL", "http://127.0.0.1:8010")
SUPPLIER = os.getenv("SUPPLIER_A_RPC_URL", "http://127.0.0.1:8011/rpc")


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        h = await client.get(f"{BUYER}/health")
        h.raise_for_status()
        print("buyer health:", h.json())

        base = SUPPLIER.rsplit("/rpc", 1)[0]
        sh = await client.get(f"{base}/health")
        sh.raise_for_status()
        print("supplier health:", sh.json())

        pr = await client.post(
            f"{BUYER}/api/purchases",
            json={"product_name": "重型脚轮", "quantity": 500, "approve": True},
        )
        pr.raise_for_status()
        created = pr.json()
        business_id = created["business_id"]
        print("created:", business_id)
        assert "budget" in created["purchase_request"]

        rfq = await client.post(
            f"{BUYER}/api/purchases/{business_id}/rfq",
            json={
                "business_id": business_id,
                "partner_url": SUPPLIER,
                "supplier_aic": "supplier-a-local-aic",
            },
        )
        rfq.raise_for_status()
        rfq_body = rfq.json()
        print("rfq:", json.dumps(rfq_body, ensure_ascii=False, indent=2))
        assert rfq_body.get("quote"), "expected quote envelope"
        assert rfq_body["quote"]["schema_type"] == "agentlink.initial_quote"
        assert "budget" not in (rfq_body["quote"].get("payload") or {})
        assert rfq_body["quote"]["payload"].get("shipping_cost") is None

        cmp_ = await client.get(f"{BUYER}/api/purchases/{business_id}/comparison")
        cmp_.raise_for_status()
        print("comparison:", json.dumps(cmp_.json(), ensure_ascii=False, indent=2))

        draft = await client.post(f"{BUYER}/api/purchases/{business_id}/order-draft")
        draft.raise_for_status()
        draft_body = draft.json()
        print("draft:", json.dumps(draft_body, ensure_ascii=False, indent=2))
        assert draft_body["schema_type"] == "agentlink.order_draft"
        assert draft_body["payload"]["status"] == "ORDER_DRAFT"
        assert draft_body["payload"]["activate_allowed"] is False

        act = await client.post(f"{BUYER}/api/purchases/{business_id}/activate")
        assert act.status_code == 400, f"activate must be blocked, got {act.status_code}"
        print("activate blocked:", act.json())

        aud = await client.get(f"{BUYER}/api/purchases/{business_id}/audit")
        aud.raise_for_status()
        events = aud.json()["events"]
        print("audit events:", len(events))
        tools = {e["tool"] for e in events}
        assert "send_rfq" in tools
        assert "create_order_draft" in tools
        assert "activate_order" in tools

    print("SMOKE_OK")


if __name__ == "__main__":
    asyncio.run(main())
