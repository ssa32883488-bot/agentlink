# -*- coding: utf-8 -*-
"""Smoke combo RFQ (casters + chair frame) against A+C — identity must pass."""
from __future__ import annotations

from pathlib import Path
import os

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

SMOKE = r"""
set -a
. /opt/agentlink/.env
. /etc/agentlink/buyer-a.env
set +a
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, os
from commerce.buyer_tools.service import get_buyer_tools

async def main():
    tools = get_buyer_tools()
    # force shortlist a+c with live AICs via env map
    disc = await tools.discover_suppliers_tool({
        'product_name': '重型脚轮与钢管制件椅架',
        'quantity': 700,
        'query': '脚轮 椅架 供应商',
        'limit': 5,
        'refresh': True,
        'lines': [
            {'sku': 'RM-CASTER-300', 'name': '重型脚轮', 'qty': 500},
            {'sku': 'RM-FRAME-STEEL', 'name': '钢管制件椅架', 'qty': 200},
        ],
    })
    case_id = disc.get('case_id')
    cands = disc.get('candidates') or []
    print('discover', disc.get('source'), 'n', len(cands), 'case', case_id)
    for c in cands:
        print('cand', c.get('agent_id'), (c.get('aic') or '')[-20:], 'ep', c.get('endpoint'))
    # Prefer A+C; if discover empty, explicit ids
    selected = []
    for c in cands:
        aid = c.get('agent_id') or ''
        cid = c.get('candidate_id')
        if aid in ('supplier-a', 'supplier-c') and cid:
            selected.append(cid)
    if len(selected) < 2:
        selected = ['supplier-a', 'supplier-c']
    out = await tools.rfq_send_batch({'case_id': case_id, 'selected': selected})
    rows = []
    id_fail = 0
    ok_n = 0
    for q in out.get('quotes') or []:
        p = q.get('partner') or {}
        err = q.get('error') or ''
        if '身份' in err or 'senderId' in err or 'peer AIC' in err or 'expected_partner' in err or 'TLS server AIC' in err:
            id_fail += 1
        if q.get('status') == 'ok' or q.get('goods_total') is not None:
            ok_n += 1
        rows.append({
            'partner': p.get('name') or p.get('agent_id'),
            'sku': q.get('sku') or (q.get('product') or {}).get('sku'),
            'status': q.get('status'),
            'goods': q.get('goods_total'),
            'err': err[:200],
        })
    print(json.dumps({'ok': out.get('ok'), 'ok_n': ok_n, 'id_fail': id_fail, 'rows': rows}, ensure_ascii=False))
    print('IDENTITY_PASS' if id_fail == 0 and ok_n >= 1 else 'IDENTITY_FAIL')

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
    _, o, e = b.exec_command(SMOKE, timeout=300, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    b.close()


if __name__ == "__main__":
    main()
