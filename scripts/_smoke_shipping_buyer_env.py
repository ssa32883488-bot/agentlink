# -*- coding: utf-8 -*-
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
HOST = "81.70.46.119"

REMOTE = r"""
set -e
cd /opt/agentlink
set -a
. /opt/agentlink/.env
. /etc/agentlink/buyer-a.env
set +a
export BUYER_AGENT_ID=buyer-a
/opt/agentlink/.venv/bin/python - <<'PY'
import asyncio, os, sys
sys.path.insert(0, '/opt/agentlink')
os.chdir('/opt/agentlink')
print('LOGISTICS_AIC', os.getenv('LOGISTICS_AIC'))
print('CERT', os.getenv('AIP_CLIENT_CERT'))
from commerce import procurement_case as pc
from commerce import flow_service as fs
from commerce.seat_catalog import product_physical_specs
from agentlink_runtime.aip_payload import wrap_business

async def main():
    phys = product_physical_specs('RM-CASTER-300', qty=500)
    case = fs.create_from_brief(product_name='重型脚轮300kg', quantity=500, note='smoke-ship-mtls')
    cid = case['case_id']
    draft = wrap_business('agentlink.order_draft', cid, {
        'draft_id': f'draft-{cid}',
        'sku': 'RM-CASTER-300',
        'product_name': '重型脚轮300kg',
        'quantity': 500,
        'unit_price': 18,
        'goods_total': 9000,
        'weight_kg': phys['weight_kg'],
        'volume_m3': phys['volume_m3'],
        'kg_per_unit': phys['kg_per_unit'],
        'charge_class': phys['charge_class'],
        'shipping_unknown': True,
        'supplier_agent_id': 'supplier-a',
    })
    pc.update_case(cid, state='ORDER_DRAFT', order_draft=draft, selected_supplier='supplier-a')
    try:
        out = await fs.step_shipping(cid, weight_kg=200.0, postal_code='071000')
    except Exception as exc:
        print('EXC', type(exc).__name__, exc)
        raise SystemExit(2)
    ship = ((out.get('shipping_quote') or {}).get('payload') or {})
    print('STATE', out.get('state'), 'COST', ship.get('shipping_cost'), 'W', ship.get('weight_kg'), 'V', ship.get('volume_m3'))
    ok = out.get('state') == 'CONTRACT_PENDING' and ship.get('shipping_cost') is not None
    print('PASS' if ok else 'FAIL')
    if not ok:
        print('SHIP', ship)
    raise SystemExit(0 if ok else 1)

asyncio.run(main())
PY
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(REMOTE, timeout=120)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    main()
