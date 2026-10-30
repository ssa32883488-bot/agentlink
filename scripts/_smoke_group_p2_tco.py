# -*- coding: utf-8 -*-
"""P2：Group 盲拍 + 同组物流 TCO + 模拟选商下单数据源。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
ROOT = Path(__file__).resolve().parents[1]
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE = r"""
set -e
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import asyncio, json, os, sys
os.chdir('/opt/agentlink')
sys.path.insert(0,'/opt/agentlink')
from agentlink_runtime.aip_payload import wrap_business
from commerce import group_mq as gm
from commerce.env_loader import load_dotenv

async def main():
    load_dotenv()
    leader=os.environ['BUYER_A_AIC']
    env=wrap_business('agentlink.blind_bid','smoke-p2',{
        'auction_id':'auc-smoke-p2','product_name':'重型脚轮','quantity':500,
        'specifications':{'rated_load_kg_min':300},'sealed':True,
    })
    out=await gm.run_group_blind_auction(
        leader_aic=leader, leader_agent_id='buyer-a',
        member_agent_ids=['supplier-a','supplier-b','supplier-c','logistics'],
        bid_envelope=env, with_tco=True, dest_postal='071000', quantity=500, wait_sec=50,
    )
    print(json.dumps({
        'bids':[{k:b.get(k) for k in ('supplier_agent_id','unit_price','shipping_cost','tco','error')} for b in out.get('bids') or []],
        'schemes': out.get('schemes') or [],
        'ranked_ids':[b.get('supplier_agent_id') for b in out.get('ranked') or []],
    }, ensure_ascii=False, default=str))
    schemes=out.get('schemes') or []
    with_tco=[s for s in schemes if s.get('tco') is not None]
    priced=[b for b in out.get('bids') or [] if b.get('unit_price') is not None]
    ok=len(priced)>=3 and len(with_tco)>=3
    print('PASS' if ok else 'FAIL', 'priced', len(priced), 'tco', len(with_tco))
    raise SystemExit(0 if ok else 1)
asyncio.run(main())
PY
"""


def put(c, files):
    sftp = c.open_sftp()
    for rel in files:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()


def main() -> int:
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(
        b,
        [
            "commerce/group_mq.py",
            "commerce/flow_service.py",
            "agentlink_runtime/partner_app.py",
        ],
    )
    _, o, e = b.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-logistics; sleep 4; true",
        timeout=60,
        get_pty=True,
    )
    o.channel.recv_exit_status()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(s, ["commerce/group_mq.py", "agentlink_runtime/partner_app.py"])
    _, o, e = s.exec_command(
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 4; true",
        timeout=60,
        get_pty=True,
    )
    o.channel.recv_exit_status()
    s.close()

    _, o, e = b.exec_command(REMOTE, timeout=240, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    code = o.channel.recv_exit_status()
    b.close()
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
