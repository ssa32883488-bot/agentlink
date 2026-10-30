"""Buyer host: rfq_send_batch should get freight_amount from suppliers."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

CHECK = r"""
set -a
[ -f /opt/agentlink/.env ] && . /opt/agentlink/.env
# 与 systemd 一致：加载 buyer 出站证书
for f in /etc/agentlink/buyer-a.env /etc/agentlink/buyer.env; do
  [ -f "$f" ] && . "$f"
done
set +a
cd /opt/agentlink
echo "client_cert=${AIP_CLIENT_CERT:-unset}"
echo "insecure=${AIP_SSL_INSECURE:-unset}"
echo "identity=${AIP_IDENTITY_BINDING:-unset}"
/opt/agentlink/.venv/bin/python - <<'PY'
import asyncio, json, os
print('env_cert', bool(os.getenv('AIP_CLIENT_CERT')), 'bundle', bool(os.getenv('AIP_TRUST_BUNDLE')))
from commerce.buyer_tools.service import get_buyer_tools

async def main():
    tools = get_buyer_tools()
    disc = await tools.discover_suppliers_tool({
        'product_name': '重型脚轮', 'quantity': 500, 'query': '脚轮 供应商', 'limit': 5, 'refresh': True,
    })
    print('discover', disc.get('source'), 'n', len(disc.get('candidates') or []), 'case', disc.get('case_id'))
    cands = disc.get('candidates') or []
    for c in cands[:3]:
        print('cand', c.get('candidate_id'), c.get('endpoint'))
    selected = [c.get('candidate_id') for c in cands[:3] if c.get('candidate_id')]
    if not selected:
        selected = ['supplier-a', 'supplier-b', 'supplier-c']
    out = await tools.rfq_send_batch({'case_id': disc.get('case_id'), 'selected': selected})
    rows = []
    for q in out.get('quotes') or []:
        p = q.get('partner') or {}
        fr = q.get('freight') or {}
        rows.append({
            'name': p.get('name') or p.get('agent_id'),
            'status': q.get('status'),
            'goods': q.get('goods_total'),
            'freight': fr.get('amount') if isinstance(fr, dict) else q.get('freight_amount'),
            'grand': q.get('grand_total'),
            'err': (q.get('error') or '')[:120],
        })
    print(json.dumps({
        'ok': out.get('ok'),
        'parallel': out.get('parallel'),
        'summary': out.get('summary'),
        'ui': (out.get('ui_hint') or {}).get('view'),
        'rows': rows,
    }, ensure_ascii=False))

asyncio.run(main())
PY
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(CHECK, timeout=240, get_pty=True)
    print(o.read().decode("utf-8", errors="replace"))
    err = e.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR", err)
    c.close()


if __name__ == "__main__":
    main()
