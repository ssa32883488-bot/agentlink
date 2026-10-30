# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from pathlib import Path
import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
CMD = r"""
set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a
cd /opt/agentlink
.venv/bin/python <<'PY'
import asyncio, json, os, sys
sys.path.insert(0,'/opt/agentlink')
from commerce.env_loader import load_dotenv
load_dotenv()
print('DISCOVERY_ALLOW_LOCAL', os.getenv('DISCOVERY_ALLOW_LOCAL'))
print('ADP_URL', (os.getenv('ADP_URL') or os.getenv('ACPS_ADP_URL') or '')[:80])
for k in ('SUPPLIER_A_AIC','SUPPLIER_B_AIC','SUPPLIER_C_AIC','SUPPLIER_A_RPC_URL','SUPPLIER_B_RPC_URL','SUPPLIER_C_RPC_URL'):
    print(k, '=', (os.environ.get(k) or '')[-40:])
from commerce.discovery import discover_suppliers
async def main():
    for q in ['脚轮','重型脚轮300kg','RM-CASTER']:
        r = await discover_suppliers(q, limit=5, bypass_cache=True)
        cands = r.get('candidates') or []
        print('---', q, '---')
        print(json.dumps({
            'source': r.get('source'),
            'n': len(cands),
            'degrade': r.get('degrade'),
            'platform_error': r.get('platform_error'),
            'elapsed_ms': r.get('elapsed_ms') or r.get('elapsed_ms_platform'),
            'ids': [(c.get('agent_id'), (c.get('aic') or '')[-12:], c.get('source')) for c in cands[:5]],
        }, ensure_ascii=False))
asyncio.run(main())
PY
"""

def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("81.70.46.119", username="root",
              pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
              timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(CMD, timeout=120, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()

if __name__ == "__main__":
    main()
