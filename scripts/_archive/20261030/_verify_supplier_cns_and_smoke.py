# -*- coding: utf-8 -*-
"""Verify Aliyun supplier TLS CNs match env AICs, then RFQ smoke from Tencent."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

ALIYUN = r"""
for port in 8011 8013 8014; do
  echo -- $port --
  echo | timeout 8 openssl s_client -connect 127.0.0.1:$port 2>/dev/null | openssl x509 -noout -subject
done
grep -E '^SUPPLIER_[ABC]_AIC=' /opt/agentlink/.env
"""

SMOKE = r"""
set -a
. /opt/agentlink/.env
. /etc/agentlink/buyer-a.env
set +a
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, os
print('expect_a', os.getenv('SUPPLIER_A_AIC','')[-28:])
print('expect_c', os.getenv('SUPPLIER_C_AIC','')[-28:])
print('bind', os.getenv('AIP_IDENTITY_BINDING'), 'insecure', os.getenv('AIP_SSL_INSECURE'))
from commerce.buyer_tools.service import get_buyer_tools

async def main():
    tools = get_buyer_tools()
    disc = await tools.discover_suppliers_tool({
        'product_name': '重型脚轮', 'quantity': 500, 'query': '脚轮 供应商', 'limit': 5, 'refresh': True,
    })
    cands = disc.get('candidates') or []
    print('discover', disc.get('source'), 'n', len(cands), 'case', disc.get('case_id'))
    for c in cands[:3]:
        print('cand', c.get('agent_id') or c.get('candidate_id'), (c.get('aic') or '')[-28:], c.get('endpoint'))
    selected = [c.get('candidate_id') for c in cands[:3] if c.get('candidate_id')] or ['supplier-a','supplier-b','supplier-c']
    out = await tools.rfq_send_batch({'case_id': disc.get('case_id'), 'selected': selected})
    rows = []
    ok_n = 0
    for q in out.get('quotes') or []:
        p = q.get('partner') or {}
        fr = q.get('freight') or {}
        goods = q.get('goods_total')
        if goods is not None:
            ok_n += 1
        rows.append({
            'name': p.get('name') or p.get('agent_id'),
            'status': q.get('status'),
            'goods': goods,
            'freight': fr.get('amount') if isinstance(fr, dict) else q.get('freight_amount'),
            'err': (q.get('error') or '')[:180],
        })
    print(json.dumps({'ok': out.get('ok'), 'ok_n': ok_n, 'rows': rows}, ensure_ascii=False))
    print('RFQ_PASS' if ok_n >= 2 else 'RFQ_FAIL')

asyncio.run(main())
PY
"""


def main() -> None:
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = s.exec_command(ALIYUN, timeout=60)
    print("ALIYUN\n", (o.read() + e.read()).decode("utf-8", "replace"))
    s.close()

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
    _, o, e = b.exec_command(SMOKE, timeout=240, get_pty=True)
    print("SMOKE\n", (o.read() + e.read()).decode("utf-8", "replace"))
    b.close()


if __name__ == "__main__":
    main()
