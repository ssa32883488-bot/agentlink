# -*- coding: utf-8 -*-
"""完整 case 冒烟：发现→短名单→RFQ→组群竞价(TCO)→选商下单。"""
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
sys.path.insert(0, '/opt/agentlink')

from commerce.env_loader import load_dotenv
from commerce import flow_service as fs
from commerce import procurement_case as pc

async def main():
    load_dotenv()
    case = fs.create_from_brief(product_name='重型脚轮', quantity=500, rated_load_kg_min=300, note='e2e-group-smoke')
    cid = case['case_id']
    print('CASE', cid, flush=True)

    # DRAFT → DISCOVERING → SHORTLIST_PENDING
    case = await fs.step_discover(cid, bypass_cache=True)
    print('DISCOVER', case['state'], 'cand', len(case.get('candidates') or []), 'src', (case.get('discovery_meta') or {}).get('source'), flush=True)

    ids = ['supplier-a', 'supplier-b', 'supplier-c']
    case = fs.step_confirm_shortlist(cid, ids)
    print('SHORTLIST', case['state'], [p.get('agent_id') for p in case.get('shortlist') or []], flush=True)

    case = await fs.step_rfq(cid)
    print('RFQ', case['state'], 'quotes', len(case.get('quotes') or []), flush=True)

    case = fs.step_decide(cid, 'auction')
    print('DECIDE_AUCTION', case['state'], flush=True)

    case = await fs.step_auction(cid)
    summary = case.get('auction_summary') or {}
    schemes = summary.get('schemes') or []
    bids = case.get('auction_bids') or []
    priced = [b for b in bids if b.get('unit_price') is not None]
    print('AUCTION', case['state'], 'transport', summary.get('transport'), 'priced', len(priced), 'schemes', len(schemes), flush=True)
    if schemes:
        print('BEST', schemes[0].get('supplier_agent_id'), 'tco', schemes[0].get('tco'), 'ship', schemes[0].get('shipping_cost'), flush=True)

    # BID_REVIEW → order via best TCO
    case = fs.step_decide(cid, 'order')  # default = schemes[0]
    draft = (case.get('order_draft') or {}).get('payload') or {}
    print('ORDER', case['state'], 'supplier', case.get('selected_supplier'),
          'unit', draft.get('unit_price'), 'ship', draft.get('shipping_cost'),
          'goods', draft.get('goods_total'), 'ticket', case.get('order_ticket_id'), flush=True)

    ok = (
        case['state'] == 'ORDER_DRAFT'
        and summary.get('transport') == 'group'
        and len(priced) >= 3
        and len(schemes) >= 3
        and draft.get('shipping_cost') is not None
        and case.get('selected_supplier') == (schemes[0].get('supplier_agent_id') if schemes else None)
    )
    print('PASS' if ok else 'FAIL', json.dumps({
        'case_id': cid,
        'transport': summary.get('transport'),
        'schemes': [{k: s.get(k) for k in ('supplier_agent_id','unit_price','shipping_cost','tco')} for s in schemes],
        'selected': case.get('selected_supplier'),
        'draft_ship': draft.get('shipping_cost'),
        'ticket': case.get('order_ticket_id'),
    }, ensure_ascii=False), flush=True)
    raise SystemExit(0 if ok else 1)

asyncio.run(main())
PY
"""


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()


def main() -> int:
    # ensure latest flow + group on both clouds
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
        "systemctl restart agentlink-buyer-a agentlink-logistics; sleep 3; systemctl is-active agentlink-buyer-a",
        timeout=60,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")

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
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 3; true",
        timeout=60,
        get_pty=True,
    )
    o.channel.recv_exit_status()
    s.close()

    print("==== E2E case smoke ====", flush=True)
    _, o, e = b.exec_command(REMOTE, timeout=360, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    code = o.channel.recv_exit_status()
    b.close()
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
