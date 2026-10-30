# -*- coding: utf-8 -*-
"""Smoke: order draft with SKU specs → request_shipping derives weight → logistics quotes."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
HOST = "81.70.46.119"

REMOTE = r"""
cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'
import asyncio, os, sys
sys.path.insert(0, '/opt/agentlink')
os.chdir('/opt/agentlink')
from commerce.env_loader import load_dotenv
load_dotenv()
from commerce import procurement_case as pc
from commerce import flow_service as fs
from commerce.seat_catalog import product_physical_specs
from agentlink_runtime.aip_payload import wrap_business

async def main():
    phys = product_physical_specs('RM-CASTER-300', qty=500)
    assert phys.get('weight_kg') == 200.0, phys
    case = fs.create_from_brief(product_name='重型脚轮300kg', quantity=500, note='smoke-ship-specs')
    cid = case['case_id']
    # jump to ORDER_DRAFT with full specs on draft
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
    pc.update_case(cid, state='ORDER_DRAFT', order_draft=draft, selected_supplier='supplier-a',
                   brief={**case['brief'], 'lines':[{'sku':'RM-CASTER-300','name':'重型脚轮300kg','qty':500}]})
    mass = fs._shipping_mass_from_case(pc.get_case(cid))
    print('MASS', mass, flush=True)
    assert abs(float(mass['weight_kg']) - 200.0) < 1e-6, mass
    out = await fs.step_shipping(cid, weight_kg=200.0, postal_code='071000')
    ship = ((out.get('shipping_quote') or {}).get('payload') or {})
    print('STATE', out.get('state'), 'COST', ship.get('shipping_cost'), 'W', ship.get('weight_kg'), flush=True)
    ok = out.get('state') == 'CONTRACT_PENDING' and ship.get('shipping_cost') is not None
    if not ok:
        print('RAW', {k: out.get(k) for k in ('state','hitl_pending')}, 'ship_keys', list(ship.keys())[:20], flush=True)
        # also show last error if identity
        print('SHIP_PAY', ship, flush=True)
    print('PASS' if ok else 'FAIL', flush=True)
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
    # ensure smoke helpers exist on server
    sftp = c.open_sftp()
    # flow_service already deployed with _shipping_mass_from_case
    sftp.close()
    _, o, e = c.exec_command(REMOTE, timeout=120)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    main()
