# -*- coding: utf-8 -*-
"""P0 本地冒烟：同进程 Leader 建组 + Partner.join_group + ping 回执（直连 wt.ioa.pub MQ）。"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from commerce.env_loader import load_dotenv  # noqa: E402
from commerce import group_mq as gm  # noqa: E402


async def main() -> int:
    load_dotenv()
    leader_aic = os.getenv("BUYER_A_AIC", "").strip()
    if not leader_aic:
        print("FAIL: BUYER_A_AIC missing")
        return 2

    print("MQ config:", gm.mq_rabbit_config(), flush=True)
    print("open_group_inprocess_join ...", flush=True)
    rec = await gm.open_group_inprocess_join(
        leader_aic=leader_aic,
        leader_agent_id="buyer-a",
        member_agent_ids=["supplier-a", "supplier-b", "supplier-c", "logistics"],
    )
    print(
        "session",
        rec.session_id,
        "group",
        rec.group_id,
        "members",
        rec.members,
        flush=True,
    )
    joined = [m for m in rec.members if m.get("status") == "joined"]
    if len(joined) < 4:
        print("FAIL: not all joined", rec.members)
        await gm.dissolve_group(rec.session_id)
        return 1

    print("ping_group ...", flush=True)
    out = await gm.ping_group(rec.session_id)
    print("ping out:", out, flush=True)
    got = set(out.get("got") or [])
    expected = set(out.get("expected") or [])
    ok = bool(expected) and expected.issubset(got)
    await gm.dissolve_group(rec.session_id)
    if ok:
        print("PASS: group p0 ping acks from", sorted(got))
        return 0
    print("FAIL: missing acks", "expected", sorted(expected), "got", sorted(got))
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
