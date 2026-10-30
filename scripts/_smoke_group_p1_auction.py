# -*- coding: utf-8 -*-
"""P1：跨云 Group 盲拍冒烟（建组→广播 blind_bid→三家出价）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"

REMOTE = r"""
set -e
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import asyncio, json, os, sys
os.chdir('/opt/agentlink')
sys.path.insert(0, '/opt/agentlink')
from agentlink_runtime.aip_payload import wrap_business
from commerce import group_mq as gm
from commerce.env_loader import load_dotenv

async def main():
    load_dotenv()
    leader = os.environ['BUYER_A_AIC']
    env = wrap_business('agentlink.blind_bid', 'smoke-p1', {
        'auction_id': 'auc-smoke-p1',
        'product_name': '重型脚轮',
        'quantity': 500,
        'specifications': {'rated_load_kg_min': 300},
        'sealed': True,
    })
    out = await gm.run_group_blind_auction(
        leader_aic=leader,
        leader_agent_id='buyer-a',
        member_agent_ids=['supplier-a','supplier-b','supplier-c','logistics'],
        bid_envelope=env,
        wait_sec=40,
    )
    print(json.dumps(out, ensure_ascii=False, default=str))
    priced = [b for b in out.get('bids') or [] if b.get('unit_price') is not None]
    ok = len(priced) >= 3
    print('PASS' if ok else 'FAIL', 'priced', len(priced), 'got', out.get('offers_got'))
    raise SystemExit(0 if ok else 1)

asyncio.run(main())
PY
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    # upload latest group + flow files first via sftp
    root = Path(__file__).resolve().parents[1]
    sftp = c.open_sftp()
    for rel in (
        "commerce/group_mq.py",
        "commerce/flow_service.py",
        "agentlink_runtime/partner_app.py",
    ):
        sftp.put(str(root / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()
    _, o, e = c.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-logistics; sleep 3; true",
        timeout=60,
        get_pty=True,
    )
    o.channel.recv_exit_status()
    _, o, e = c.exec_command(REMOTE, timeout=180, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    code = o.channel.recv_exit_status()
    c.close()
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
