"""Smoke supplier freight on Aliyun (needs logistics on Tencent)."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

SUPPLIER = "39.105.20.113"
SUPPLIER_PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

CHECK = r"""
set -a
[ -f /opt/agentlink/.env ] && . /opt/agentlink/.env
[ -f /etc/agentlink/supplier-a.env ] && . /etc/agentlink/supplier-a.env
set +a
cd /opt/agentlink
echo "client_cert=${AIP_CLIENT_CERT:-unset}"
echo "logistics=${LOGISTICS_RPC_URL:-unset}"
echo "insecure=${AIP_SSL_INSECURE:-unset}"
PY=/opt/agentlink/.venv/bin/python
[ -x "$PY" ] || PY=python3
$PY - <<'PY'
import asyncio, json, os
from pathlib import Path
import yaml
from agentlink_runtime.graph_base import new_state
from agents.supplier_a.graph import run_supplier_pipeline
from commerce.discovery import discover_logistics

policy = yaml.safe_load(Path('agents/supplier_a/policy.yaml').read_text(encoding='utf-8'))

async def main():
    d = await discover_logistics()
    print('logistics_src', d.get('source'), 'n', len(d.get('candidates') or []), 'deg', d.get('degrade'))
    if d.get('candidates'):
        print('peer', d['candidates'][0].get('endpoint'), d['candidates'][0].get('aic')[-12:])
    state = new_state(
        agent_id='supplier-a',
        aic=os.getenv('SUPPLIER_A_AIC', 'supplier-a-local-aic'),
        tenant_id='supplier-org-a',
        business_id='biz-freight-smoke',
        aip_task_id='t-smoke',
        session_id='s-smoke',
        authz_level='negotiate',
    )
    env = {
        'schema_type': 'agentlink.quote_request',
        'business_id': 'biz-freight-smoke',
        'payload': {
            'purchase_request_id': 'pr-smoke-1',
            'product_name': '重型脚轮',
            'quantity': 500,
            'specifications': {'rated_load_kg_min': 300},
            'need_freight': True,
            'postal_code': '071000',
        },
    }
    out = await run_supplier_pipeline(state=state, rfq_envelope=env, policy=policy)
    pay = ((out.get('outcome') or {}).get('envelope') or {}).get('payload') or {}
    print(json.dumps({
        'aip_state': (out.get('outcome') or {}).get('aip_state'),
        'unit_price': pay.get('unit_price'),
        'freight_amount': pay.get('freight_amount'),
        'shipping_cost': pay.get('shipping_cost'),
        'distance_km': pay.get('distance_km') or (pay.get('freight') or {}).get('distance_km'),
        'freight_note': pay.get('freight_note'),
        'logistics_meta': pay.get('logistics_meta'),
    }, ensure_ascii=False))

asyncio.run(main())
PY
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        SUPPLIER,
        username="root",
        password=SUPPLIER_PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, stdout, stderr = c.exec_command(CHECK, timeout=180, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR:", err)
    c.close()


if __name__ == "__main__":
    main()
