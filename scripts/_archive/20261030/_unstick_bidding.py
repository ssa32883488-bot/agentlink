# -*- coding: utf-8 -*-
"""Finish stuck BIDDING cases via step_auction."""
from __future__ import annotations
import os
from pathlib import Path
import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
CMD = r"""
set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, sys, time
sys.path.insert(0,'/opt/agentlink')
from commerce import procurement_case as pc, flow_service as fs

async def main():
    stuck=[c for c in pc.list_cases(limit=20) if c.get('state')=='BIDDING']
    print('STUCK', [c.get('case_id') for c in stuck], flush=True)
    for c in stuck:
        cid=c['case_id']
        t0=time.perf_counter()
        try:
            out=await fs.step_auction(cid)
            s=out.get('auction_summary') or {}
            print('DONE', json.dumps({
              'case':cid,'state':out.get('state'),
              'transport':s.get('transport'),'early':s.get('early_abort'),
              'timings':s.get('timings_ms'),
              'priced':len([b for b in (out.get('auction_bids') or []) if b.get('unit_price') is not None]),
              'ms':round((time.perf_counter()-t0)*1000,1),
            },ensure_ascii=False), flush=True)
        except Exception as e:
            print('ERR', cid, type(e).__name__, str(e)[:300], flush=True)

asyncio.run(main())
PY
"""

def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("81.70.46.119", username="root",
              pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
              timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(CMD, timeout=300, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()

if __name__ == "__main__":
    main()
