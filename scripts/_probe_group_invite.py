# -*- coding: utf-8 -*-
"""Remote probe: why group invite fails; run via SSH on buyer."""
from __future__ import annotations

import asyncio
import json
import os
import traceback
import urllib.error
import urllib.request
import ssl

os.chdir("/opt/agentlink")
from commerce.env_loader import load_dotenv

load_dotenv()
for f in ("/etc/agentlink/buyer-a.env",):
    if os.path.isfile(f):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

from commerce import group_mq as gm

CTX = ssl._create_unverified_context()


def http_post(url: str, body: dict) -> tuple[int, str]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12, context=CTX) as r:
            return r.status, r.read().decode("utf-8", "replace")[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


async def main() -> None:
    print("ENV", json.dumps({
        "ACPS_GROUP_AUCTION": os.getenv("ACPS_GROUP_AUCTION"),
        "ACPS_GROUP_MIN_SUPPLIERS": os.getenv("ACPS_GROUP_MIN_SUPPLIERS"),
        "ACPS_GROUP_INVITE_TIMEOUT_SEC": os.getenv("ACPS_GROUP_INVITE_TIMEOUT_SEC"),
        "BUYER_A_AIC": (os.getenv("BUYER_A_AIC") or "")[:48],
    }, ensure_ascii=False))
    for mid in ["supplier-a", "supplier-b", "supplier-c", "logistics"]:
        join = gm.partner_join_url(mid)
        code, body = http_post(join, {})
        print("JOIN_HTTP", mid, join, code, body[:160])

    os.environ["ACPS_GROUP_INVITE_TIMEOUT_SEC"] = "20"
    try:
        out = await gm.run_group_blind_auction(
            leader_aic=os.environ.get("BUYER_A_AIC", ""),
            leader_agent_id="buyer-a",
            member_agent_ids=["supplier-a", "supplier-c"],
            bid_envelope={
                "schema_type": "agentlink.blind_bid",
                "schema_version": "1.0",
                "business_id": "probe-group",
                "payload": {
                    "auction_id": "probe-auc",
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
        print("AUCTION", json.dumps({
            "early_abort": out.get("early_abort"),
            "abort_reason": out.get("abort_reason"),
            "offers_got": out.get("offers_got"),
            "invite_elapsed_ms": out.get("invite_elapsed_ms"),
            "joined_suppliers": out.get("joined_suppliers"),
            "members": out.get("members"),
            "priced": len([b for b in (out.get("bids") or []) if b.get("unit_price") is not None]),
            "schemes": len(out.get("schemes") or []),
        }, ensure_ascii=False, default=str))
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
