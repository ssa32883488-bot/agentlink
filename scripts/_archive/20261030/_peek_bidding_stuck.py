# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from pathlib import Path
import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
CMD = r"""
set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a
cd /opt/agentlink
.venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0,'/opt/agentlink')
from commerce import procurement_case as pc
for c in pc.list_cases(limit=10):
    st=c.get('state')
    if st not in ('BIDDING','BID_REVIEW','COMPARE_PENDING','ORDER_DRAFT','ACTIVE','CONTRACT_PENDING'):
        continue
    s=c.get('auction_summary') or {}
    print(json.dumps({
      'case':c.get('case_id'),'state':st,
      'transport':s.get('transport'),'early':s.get('early_abort'),
      'timings':s.get('timings_ms'),
      'priced':len([b for b in (c.get('auction_bids') or []) if b.get('unit_price') is not None]),
      'note':(c.get('brief') or {}).get('note') or (c.get('brief') or {}).get('product_name'),
    },ensure_ascii=False))
print('--- journal ---')
PY
journalctl -u agentlink-buyer-a --since '10 min ago' --no-pager 2>/dev/null | grep -iE 'auction|group|invite|blind|BIDDING|timeout|error|rpc' | tail -n 50
"""

def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("81.70.46.119", username="root",
              pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
              timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(CMD, timeout=90, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()

if __name__ == "__main__":
    main()
