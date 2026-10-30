# -*- coding: utf-8 -*-
"""Deploy: 初询不泄优惠 / 议价才披露 + 采购侧映射修复."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "agents/supplier_common/negotiate.py",
    "commerce/buyer_tools/service.py",
    "commerce/chat_buyer_wit.py",
    "commerce/flow_service.py",
]


def put(host: str, *, pem: bool, restart: str) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = dict(
        hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False
    )
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    sftp = c.open_sftp()
    for rel in FILES:
        local = ROOT / rel
        if local.is_file():
            sftp.put(str(local), f"/opt/agentlink/{rel}")
            print("put", host, rel, flush=True)
    sftp.close()
    _, o, e = c.exec_command(restart, timeout=120, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()


def main() -> None:
    put(
        "81.70.46.119",
        pem=True,
        restart=(
            "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
            "sleep 4; systemctl is-active agentlink-buyer-a"
        ),
    )
    put(
        "39.105.20.113",
        pem=False,
        restart=(
            "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
            "sleep 3; echo aliyun_ok; "
            "python3 - <<'PY'\n"
            "import sys; sys.path.insert(0,'/opt/agentlink')\n"
            "from agents.supplier_common.negotiate import enrich_initial_quote, handle_bargain_round\n"
            "import asyncio, yaml\n"
            "from pathlib import Path\n"
            "pol=yaml.safe_load(Path('/opt/agentlink/agents/supplier_a/policy.yaml').read_text())\n"
            "q=enrich_initial_quote({'unit_price':20,'product':{'sku':'RM-CASTER-300','quantity':300,'name':'重型脚轮'}}, pol)\n"
            "assert q.get('policy_hints') is None and q.get('promotions_disclosed') is False, q\n"
            "print('initial_ok', q.get('pricing_mode'), q.get('note')[:20])\n"
            "async def t():\n"
            "  st={'agent_id':'supplier-a','business_id':'t1'}\n"
            "  env={'schema_type':'agentlink.bargain_round','business_id':'t1','payload':{\n"
            "    'quantity':300,'product_name':'重型脚轮','sku':'RM-CASTER-300',\n"
            "    'previous_unit_price':20,'goal_text':'有没有价格优惠','need_freight':False}}\n"
            "  out=await handle_bargain_round(state=st, envelope=env, policy=pol)\n"
            "  pay=out['outcome']['envelope']['payload']\n"
            "  assert pay.get('policy') and pay['policy'].get('hints'), pay.get('policy')\n"
            "  print('bargain_ok', pay['policy']['hints'][:1], (pay.get('policy') or {}).get('reach_example'))\n"
            "asyncio.run(t())\n"
            "PY"
        ),
    )
    print("DEPLOY_BARGAIN_PHASE_DONE", flush=True)


if __name__ == "__main__":
    main()
