# -*- coding: utf-8 -*-
"""Probe why group auction for CASTER-200 yields 0 priced bids."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER = r"""
set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, os, sys
sys.path.insert(0,'/opt/agentlink')
from commerce import flow_service as fs

async def main():
    case=fs.create_from_brief(
        product_name='标准脚轮200kg', quantity=500, note='probe-auction',
        lines=[{'sku':'RM-CASTER-200','name':'标准脚轮200kg','qty':500}],
    )
    cid=case['case_id']
    case=await fs.step_discover(cid,'标准脚轮200kg', bypass_cache=True)
    print('DISC', case['state'], [(c.get('agent_id'), (c.get('aic') or '')[-12:]) for c in (case.get('candidates') or [])[:5]], flush=True)
    case=fs.step_confirm_shortlist(cid, ['supplier-a','supplier-c'])
    case=await fs.step_rfq(cid)
    quotes=[]
    for q in case.get('quotes') or []:
        p=q.get('payload') or {}
        quotes.append({'sid':p.get('supplier_agent_id'),'sku':p.get('sku') or p.get('product_name'),'unit':p.get('unit_price'),'err':p.get('error')})
    print('RFQ', case['state'], json.dumps(quotes, ensure_ascii=False), flush=True)
    case=fs.step_decide(cid,'auction')
    try:
        case=await fs.step_auction(cid)
    except Exception as e:
        print('AUC_EXC', type(e).__name__, str(e)[:300], flush=True)
        return
    summary=case.get('auction_summary') or {}
    bids=case.get('auction_bids') or []
    print('AUC', json.dumps({
        'state':case['state'],'transport':summary.get('transport'),
        'schemes':len(summary.get('schemes') or []),
        'bids':[{k:b.get(k) for k in ('supplier_agent_id','unit_price','error','transport')} for b in bids],
        'errors':summary.get('errors'),
    }, ensure_ascii=False), flush=True)

asyncio.run(main())
PY
"""


def main() -> None:
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
    _, o, e = b.exec_command(BUYER, timeout=300, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    b.close()


if __name__ == "__main__":
    main()
