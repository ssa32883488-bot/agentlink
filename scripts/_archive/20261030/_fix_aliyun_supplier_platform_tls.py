# -*- coding: utf-8 -*-
"""Point Java suppliers at platform server certs (trusted by buyer trust-bundle)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
ALIYUN = "39.105.20.113"
TENCENT = "81.70.46.119"

FIX = r"""
set -e
for u in a b c; do
  unit=/etc/systemd/system/agentlink-supplier-${u}.service
  cert=/opt/agentlink/certs/platform/supplier-${u}/server-cert.pem
  key=/opt/agentlink/certs/platform/supplier-${u}/server-key.pem
  test -f "$cert" && test -f "$key"
  # rewrite SSL_CERT / SSL_KEY lines
  sed -i "s|^Environment=SSL_CERT=.*|Environment=SSL_CERT=file:${cert}|" "$unit"
  sed -i "s|^Environment=SSL_KEY=.*|Environment=SSL_KEY=file:${key}|" "$unit"
  grep -E 'SSL_CERT|SSL_KEY' "$unit"
done
systemctl daemon-reload
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 6
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
echo '=== presented subjects ==='
for p in 8011 8013 8014; do
  echo "--- :$p ---"
  echo | timeout 6 openssl s_client -connect 127.0.0.1:$p 2>/dev/null | openssl x509 -noout -subject -issuer 2>/dev/null
done
echo '=== verify with platform trust ==='
echo | timeout 6 openssl s_client -connect 127.0.0.1:8011 -showcerts 2>/dev/null \
  | openssl x509 > /tmp/presented-a.pem
openssl verify -CAfile /opt/agentlink/certs/platform/trust-bundle.pem /tmp/presented-a.pem || true
curl -sk https://127.0.0.1:8011/health; echo
curl -sk https://127.0.0.1:8013/health; echo
curl -sk https://127.0.0.1:8014/health; echo
"""

BUYER_SMOKE = r"""
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
    disc = await tools.discover_suppliers_tool({
        'product_name': '重型脚轮', 'quantity': 500, 'query': '脚轮 供应商', 'limit': 5, 'refresh': True,
    })
    print('discover', disc.get('source'), 'n', len(disc.get('candidates') or []), 'case', disc.get('case_id'))
    cands = disc.get('candidates') or []
    selected = [c.get('candidate_id') for c in cands[:3] if c.get('candidate_id')]
    if not selected:
        selected = ['supplier-a', 'supplier-b', 'supplier-c']
    out = await tools.rfq_send_batch({'case_id': disc.get('case_id'), 'selected': selected})
    rows = []
    ok_n = 0
    for q in out.get('quotes') or []:
        p = q.get('partner') or {}
        fr = q.get('freight') or {}
        goods = q.get('goods_total')
        status = q.get('status')
        if status not in ('error', 'failed', None) and goods is not None:
            ok_n += 1
        rows.append({
            'name': p.get('name') or p.get('agent_id'),
            'status': status,
            'goods': goods,
            'freight': fr.get('amount') if isinstance(fr, dict) else q.get('freight_amount'),
            'grand': q.get('grand_total'),
            'lead': q.get('lead_time_days') or q.get('lead_days'),
            'err': (q.get('error') or '')[:180],
        })
    print(json.dumps({'ok': out.get('ok'), 'summary': out.get('summary'), 'rows': rows}, ensure_ascii=False))
    print('RFQ_OK_COUNT', ok_n)
    if ok_n >= 3:
        print('RFQ_TLS_FIXED_PASS')
    else:
        print('RFQ_TLS_FIXED_PARTIAL')

asyncio.run(main())
PY
"""


def main() -> int:
    print("==== switch Aliyun suppliers to platform TLS ====", flush=True)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ALIYUN, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(FIX, timeout=120, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out)
    c.close()
    if "active" not in out:
        print("SUPPLIER_RESTART_FAIL", flush=True)
        return 1

    print("==== buyer RFQ smoke ====", flush=True)
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        TENCENT,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o2, e2 = b.exec_command(BUYER_SMOKE, timeout=240, get_pty=True)
    o2.channel.settimeout(240)
    bout = (o2.read() + e2.read()).decode("utf-8", errors="replace")
    print(bout)
    b.close()
    ok = "RFQ_TLS_FIXED_PASS" in bout
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
