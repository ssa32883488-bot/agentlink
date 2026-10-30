# -*- coding: utf-8 -*-
"""热修：多品需求全覆盖（脚轮+坐垫）进入组群按行询价与汇总。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce_v2/demand_items.py",
    "commerce_v2/llm_rewrite.py",
    "commerce_v2/protocol_bridge.py",
    "commerce_v2/group_room.py",
    "commerce_v2/buyer_path_group.py",
    "commerce_v2/buyer_path_normal.py",
]


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    print("$", cmd[:160], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=240, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out[-3000:], flush=True)
    return out


def put_files(c: paramiko.SSHClient) -> None:
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            run(c, f"mkdir -p {Path(remote).parent.as_posix()}")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")


def main() -> None:
    cb = connect("buyer")
    put_files(cb)
    run(
        cb,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; sleep 2; "
        "systemctl is-active agentlink-buyer-a",
    )
    # 本地智力验：双品提取 + 按行报价 + 全量覆盖方案
    run(
        cb,
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "from commerce_v2.demand_items import extract_line_items, enrich_brief_items, resolve_supplier_sku\n"
        "from commerce_v2.group_room import build_summary\n"
        "from commerce_v2.partner_supplier import handle_envelope\n"
        "text='帮我采购500脚轮和400坐垫'\n"
        "items=extract_line_items(text)\n"
        "assert len(items)==2, items\n"
        "assert any('CASTER' in (x.get('sku') or '') for x in items)\n"
        "assert any('FOAM' in (x.get('sku') or '') for x in items)\n"
        "brief=enrich_brief_items({'raw':text}, text=text)\n"
        "assert brief.get('multi') is True\n"
        "bids=[]\n"
        "for sid in ('supplier-a','supplier-b','supplier-c'):\n"
        "  for line in items:\n"
        "    sku=resolve_supplier_sku(sid, line)\n"
        "    if not sku: continue\n"
        "    r=handle_envelope(sid, {'schema_type':'v2.group_bid','sku':sku,'quantity':line['qty']})\n"
        "    if r.get('bid'): bids.append(r['bid'])\n"
        "assert len(bids)>=3, bids\n"
        "s=build_summary(brief=brief, bids=bids, logistics_scheme={'shipping_cost':1,'eta_days':3}, demand_text=text)\n"
        "assert s.get('covers_all'), s\n"
        "assert not s.get('missing'), s\n"
        "split=next(p for p in s['plans'] if p['id']=='plan_split')\n"
        "assert len(split['lines'])==2, split\n"
        "names=sorted(x['name'] for x in split['lines'])\n"
        "print('OK_MULTI', brief.get('rewritten_query'))\n"
        "print('PLAN', split['label'])\n"
        "print('LINES', [(x.get('name'), x.get('supplier_id'), x.get('qty')) for x in split['lines']])\n"
        "print('BIDS', len(bids))\n"
        "PY",
    )
    # 防幻觉：用户同时点脚轮+坐垫时不得 guard_rebind 掉脚轮
    run(
        cb,
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "import asyncio\n"
        "from commerce_v2.llm_rewrite import rewrite_demand_llm\n"
        "async def main():\n"
        "  out=await rewrite_demand_llm('帮我采购500脚轮和400坐垫', 'buyer-a')\n"
        "  assert out.get('rewrite_engine') != 'llm_guard_rebind' or '脚轮' in str(out.get('raw')), out\n"
        "  items=out.get('items') or []\n"
        "  q=str(out.get('rewritten_query') or '') + str(out.get('raw') or '')\n"
        "  ok = (len(items)>=2) or ('脚轮' in q and '坐垫' in q)\n"
        "  assert ok, out\n"
        "  print('OK_REWRITE', out.get('rewrite_engine'), out.get('rewritten_query'), 'items', len(items))\n"
        "asyncio.run(main())\n"
        "PY",
    )
    cb.close()

    cs = connect("supplier")
    put_files(cs)
    run(
        cs,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 2; "
        "systemctl is-active agentlink-supplier-a",
    )
    cs.close()
    print("HOTFIX_MULTI_ITEM_GROUP_DONE", flush=True)


if __name__ == "__main__":
    main()
