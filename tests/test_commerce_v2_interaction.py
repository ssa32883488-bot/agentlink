# -*- coding: utf-8 -*-
"""交互矩阵：普通十点 + 组群 + Gate；本地 Partner 智力。"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["AGENTLINK_RUNTIME"] = "v2"
os.environ["V2_LOCAL_PARTNERS"] = "1"

from commerce_v2 import case_store, order_ids  # noqa: E402
from commerce_v2.chat_api import handle_chat  # noqa: E402
from commerce_v2.gates import ack_logistics_gate, ack_order_gate  # noqa: E402
from commerce_v2.models import Phase  # noqa: E402
from commerce_v2 import partner_supplier as psup  # noqa: E402
from commerce_v2 import partner_logistics as plog  # noqa: E402


def _shortlist_msg(*ids: str) -> str:
    return f"已确认短名单，请对以下 candidate_id 调用 rfq.send_batch：{','.join(ids)}"


async def test_partner_iq() -> None:
    q = psup.handle_envelope(
        "supplier-a", {"schema_type": "v2.initial_quote", "sku": "RM-CASTER-300", "quantity": 300}
    )
    assert q["ok"] and q["quote"]["unit_price"] == 20.0
    b = psup.handle_envelope(
        "supplier-a", {"schema_type": "v2.bargain", "sku": "RM-CASTER-300", "quantity": 500}
    )
    assert b["quote"]["promo_applied"] and abs(b["quote"]["unit_price"] - 18.0) < 1e-6
    s = psup.handle_envelope("supplier-a", {"schema_type": "v2.spec_query", "sku": "RM-CASTER-300"})
    assert s["spec"]["rated_load_kg"] == 300
    schema = plog.handle_envelope("logistics", {"schema_type": "v2.logistics_schema"})
    assert len(schema["required_fields"]) >= 5
    print("OK partner-iq")


async def test_path_normal() -> None:
    agent = "buyer-a"
    # 清案
    case_store.create_case(agent)

    r1 = await handle_chat(agent, "采购300套重型脚轮")
    assert "短名单" in r1["reply"] or "确认" in r1["reply"]
    assert r1["ui_widgets"] and r1["ui_widgets"][0]["kind"] == "shortlist_confirm"
    assert r1["case"]["state"] == Phase.SHORTLIST_PENDING.value

    r2 = await handle_chat(agent, _shortlist_msg("supplier-a", "supplier-c"))
    assert "初报" in r2["reply"] or "议价" in r2["reply"]
    assert r2["case"]["state"] == Phase.BARGAIN_ASK.value
    assert len(r2["case"].get("quotes") or []) >= 1

    r3 = await handle_chat(agent, "请帮我议价，询问优惠政策")
    assert r3["case"]["state"] == Phase.BUY_ASK.value
    assert r3["ui_widgets"]

    r4 = await handle_chat(agent, "确认购买：供应商supplier-a 数量500")
    oid = r4["case"]["order_id"]
    assert oid and r4["case"]["state"] == Phase.ORDER_DRAFT.value
    assert not order_ids.get_order(oid)["effective"]

    # 口头问不得生效
    r5 = await handle_chat(agent, "确认了吗")
    assert "effective=False" in r5["reply"] or "effective=false" in r5["reply"].lower() or "False" in r5["reply"]

    ack_order_gate(agent, oid)
    ack_order_gate("supplier-a", oid)
    o = order_ids.get_order(oid)
    assert o["effective"] is True

    r6 = await handle_chat(agent, "确认了吗")
    assert "effective=True" in r6["reply"] or r6["case"]["state"] in (
        Phase.LOGISTICS_HINT.value,
        Phase.ORDER_EFFECTIVE.value,
    )

    r7 = await handle_chat(agent, "允许询运")
    lid = r7["case"].get("logistics_id")
    assert lid
    ack_logistics_gate(agent, lid)
    ack_logistics_gate("logistics", lid)
    assert order_ids._load()["logistics"][lid]["effective"] is True  # noqa: SLF001
    print("OK path-normal", oid, lid)


async def test_path_group() -> None:
    agent = "buyer-a"
    case_store.create_case(agent)
    await handle_chat(agent, "采购300套重型脚轮")
    r = await handle_chat(agent, "我要组群竞价")
    assert r["case"]["path"] == "group"
    assert r["case"]["state"] == Phase.GROUP_ASK.value

    r2 = await handle_chat(agent, _shortlist_msg("supplier-a", "supplier-c"))
    assert "入群" in r2["reply"] or r2["case"].get("selected")

    r3 = await handle_chat(agent, "确认进行组群竞价")
    assert r3["case"]["state"] == Phase.GROUP_DECIDE.value
    assert r3["case"]["group"]["host"] == agent
    assert "local" in r3["case"]["group"]["transport"] or r3["case"]["group"]["transport"] == "group"

    r4 = await handle_chat(agent, "组群决断：与supplier-a下单")
    assert r4["case"]["order_id"]
    assert r4["case"]["group"]["logistics_joined"] is True
    assert r4["case"]["state"] == Phase.GROUP_LOGISTICS.value

    r5 = await handle_chat(agent, "完成组群物流")
    assert r5["case"]["logistics_id"]
    assert r5["case"]["state"] == Phase.GROUP_TICKETS.value
    print("OK path-group", r5["case"]["order_id"], r5["case"]["logistics_id"])


async def test_buyer_b_rewrite() -> None:
    case_store.create_case("buyer-b")
    r = await handle_chat("buyer-b", "采购100套脚轮")
    brief = r["case"]["brief"]
    assert "脚轮" in (brief.get("rewritten_query") or brief.get("name") or "")
    print("OK buyer-b rewrite", brief.get("sku"), brief.get("rewritten_query"))


async def main() -> None:
    await test_partner_iq()
    await test_path_normal()
    await test_path_group()
    await test_buyer_b_rewrite()
    print("ALL PASS")


if __name__ == "__main__":
    asyncio.run(main())
