# -*- coding: utf-8 -*-
"""Quick group invite health check on buyer."""
from __future__ import annotations

import asyncio
import json
import os
import sys

os.chdir("/opt/agentlink")
sys.path.insert(0, "/opt/agentlink")
from commerce.env_loader import load_dotenv

load_dotenv()
for f in ("/etc/agentlink/buyer-a.env",):
    if os.path.isfile(f):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"')

os.environ["ACPS_GROUP_INVITE_TIMEOUT_SEC"] = "30"
os.environ["ACPS_GROUP_MIN_SUPPLIERS"] = "1"

from commerce import group_mq as gm


async def main() -> None:
    out = await gm.run_group_blind_auction(
        leader_aic=os.environ.get("BUYER_A_AIC", ""),
        leader_agent_id="buyer-a",
        member_agent_ids=["supplier-a", "supplier-c"],
        bid_envelope={
            "schema_type": "agentlink.blind_bid",
            "schema_version": "1.0",
            "business_id": "probe2",
            "payload": {
                "auction_id": "probe2",
                "product_name": "标准脚轮200kg",
                "sku": "RM-CASTER-200",
                "quantity": 500,
                "sealed": True,
            },
        },
        with_tco=True,
        dest_postal="071000",
        quantity=500,
    )
    print(
        json.dumps(
            {
                "early_abort": out.get("early_abort"),
                "abort_reason": out.get("abort_reason"),
                "invite_ms": out.get("invite_elapsed_ms"),
                "members": out.get("members"),
                "priced": len([b for b in (out.get("bids") or []) if b.get("unit_price") is not None]),
                "schemes": len(out.get("schemes") or []),
                "offers": out.get("offers_got"),
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
