# -*- coding: utf-8 -*-
"""Append Aliyun self-signed leaf into buyer trust-bundle; smoke RFQ."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
ALIYUN = "39.105.20.113"
TENCENT = "81.70.46.119"

ENSURE = r"""
set -e
# ensure units still on self-signed (after failed platform attempt)
for u in a b c; do
  unit=/etc/systemd/system/agentlink-supplier-${u}.service
  if ! grep -q 'SSL_CERT=file:/etc/agentlink/tls/server.crt' "$unit"; then
    sed -i 's|^Environment=SSL_CERT=.*|Environment=SSL_CERT=file:/etc/agentlink/tls/server.crt|' "$unit"
    sed -i 's|^Environment=SSL_KEY=.*|Environment=SSL_KEY=file:/etc/agentlink/tls/server.key|' "$unit"
    need_reload=1
  fi
done
if [ "${need_reload:-0}" = 1 ]; then
  systemctl daemon-reload
  systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
  sleep 8
fi
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for i in 1 2 3 4 5 6 7 8; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8011/health || true)
  echo "try$i health=$code"
  [ "$code" = 200 ] && break
  sleep 2
done
# dump cert via python (more reliable than openssl pipe timing)
python3 - <<'PY'
import ssl, socket
ctx=ssl._create_unverified_context()
with ctx.wrap_socket(socket.create_connection(('127.0.0.1',8011), timeout=10), server_hostname='127.0.0.1') as s:
    der=s.getpeercert(binary_form=True)
open('/tmp/aliyun-selfsigned.der','wb').write(der)
print('der_bytes', len(der))
PY
openssl x509 -inform DER -in /tmp/aliyun-selfsigned.der -out /tmp/aliyun-selfsigned.pem
openssl x509 -in /tmp/aliyun-selfsigned.pem -noout -subject -issuer
wc -c /tmp/aliyun-selfsigned.pem
echo CERT_READY
"""

MERGE_SMOKE = r"""
set -e
set -a
. /opt/agentlink/.env
. /etc/agentlink/buyer-a.env
set +a
BASE=/opt/agentlink/certs/platform
test -f /tmp/aliyun-selfsigned.pem
# build runtime trust = original platform + aliyun leaf
# Prefer pristine platform bundle if present; else strip previous merge by using trust-bundle.pem
cat "$BASE/trust-bundle.pem" /tmp/aliyun-selfsigned.pem > "$BASE/trust-bundle-runtime.pem"
# also fetch b/c leaves in case they differ (same file today)
python3 - <<'PY'
import ssl, socket, subprocess
from pathlib import Path
ctx=ssl._create_unverified_context()
pem_path=Path('/opt/agentlink/certs/platform/trust-bundle-runtime.pem')
base=pem_path.read_text(encoding='utf-8')
extra=[]
for port in (8013,8014):
    with ctx.wrap_socket(socket.create_connection(('39.105.20.113',port), timeout=10), server_hostname='39.105.20.113') as s:
        der=s.getpeercert(binary_form=True)
    p=Path(f'/tmp/aliyun-{port}.der'); p.write_bytes(der)
    out=subprocess.check_output(['openssl','x509','-inform','DER','-in',str(p)], text=True)
    if out.strip() not in base and out.strip() not in ''.join(extra):
        extra.append(out if out.endswith('\n') else out+'\n')
if extra:
    pem_path.write_text(base + ''.join(extra), encoding='utf-8')
    print('appended_extra', len(extra))
else:
    print('no_extra_leaves')
print('runtime_bytes', pem_path.stat().st_size)
PY
openssl verify -CAfile "$BASE/trust-bundle-runtime.pem" /tmp/aliyun-selfsigned.pem

for f in /etc/agentlink/buyer-a.env /etc/agentlink/buyer-b.env; do
  [ -f "$f" ] || continue
  grep -q '^AIP_TRUST_BUNDLE=' "$f" \
    && sed -i 's|^AIP_TRUST_BUNDLE=.*|AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem|' "$f" \
    || echo 'AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem' >> "$f"
  grep -q '^AIP_SSL_INSECURE=' "$f" && sed -i 's|^AIP_SSL_INSECURE=.*|AIP_SSL_INSECURE=0|' "$f" || echo 'AIP_SSL_INSECURE=0' >> "$f"
  echo "updated $f"
  grep -E 'AIP_TRUST_BUNDLE|AIP_SSL_INSECURE' "$f"
done

systemctl restart agentlink-buyer-a
systemctl restart agentlink-buyer-b 2>/dev/null || true
sleep 5
systemctl is-active agentlink-buyer-a

# refresh shell env from files for smoke
set -a
. /opt/agentlink/.env
. /etc/agentlink/buyer-a.env
set +a
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, os, ssl, urllib.request
from pathlib import Path

for f in ('/opt/agentlink/.env','/etc/agentlink/buyer-a.env'):
    for raw in Path(f).read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")

print('TRUST', os.getenv('AIP_TRUST_BUNDLE'))
from agentlink_runtime.mtls import build_client_ssl_context
ctx=build_client_ssl_context()
print('ctx', bool(ctx), 'mode', getattr(ctx,'verify_mode',None))
try:
    with urllib.request.urlopen(urllib.request.Request('https://39.105.20.113:8011/health'), context=ctx, timeout=20) as r:
        print('health_verified', r.status, r.read()[:100])
except Exception as e:
    print('health_verified_FAIL', type(e).__name__, str(e)[:250])

from commerce.buyer_tools.service import get_buyer_tools

async def main():
    tools=get_buyer_tools()
    disc=await tools.discover_suppliers_tool({
        'product_name':'重型脚轮','quantity':500,'query':'脚轮 供应商','limit':5,'refresh':True,
    })
    print('discover', disc.get('source'), 'n', len(disc.get('candidates') or []), 'case', disc.get('case_id'))
    cands=disc.get('candidates') or []
    selected=[c.get('candidate_id') for c in cands[:3] if c.get('candidate_id')] or ['supplier-a','supplier-b','supplier-c']
    out=await tools.rfq_send_batch({'case_id': disc.get('case_id'), 'selected': selected})
    rows=[]; ok_n=0
    for q in out.get('quotes') or []:
        p=q.get('partner') or {}
        fr=q.get('freight') or {}
        goods=q.get('goods_total'); err=q.get('error') or ''
        if goods is not None:
            ok_n += 1
        rows.append({
            'name': p.get('name') or p.get('agent_id'),
            'status': q.get('status'),
            'goods': goods,
            'freight': fr.get('amount') if isinstance(fr, dict) else q.get('freight_amount'),
            'grand': q.get('grand_total'),
            'lead': q.get('lead_time_days') or q.get('lead_days'),
            'err': err[:180],
        })
    print(json.dumps({'ok': out.get('ok'), 'summary': out.get('summary'), 'rows': rows}, ensure_ascii=False))
    print('RFQ_OK_COUNT', ok_n)
    print('RFQ_TLS_FIXED_PASS' if ok_n >= 3 else 'RFQ_TLS_FIXED_PARTIAL')

asyncio.run(main())
PY
"""


def main() -> int:
    print("==== ensure Aliyun self-signed + export leaf ====", flush=True)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ALIYUN, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(ENSURE, timeout=120, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out)
    if "CERT_READY" not in out:
        c.close()
        return 1
    sftp = c.open_sftp()
    with sftp.file("/tmp/aliyun-selfsigned.pem", "r") as f:
        data = f.read()
        leaf = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
    sftp.close()
    c.close()

    print("==== merge trust on Tencent buyer + RFQ ====", flush=True)
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
    sftp = b.open_sftp()
    with sftp.file("/tmp/aliyun-selfsigned.pem", "w") as f:
        f.write(leaf)
    sftp.close()
    _, o2, e2 = b.exec_command(MERGE_SMOKE, timeout=300, get_pty=True)
    o2.channel.settimeout(300)
    bout = (o2.read() + e2.read()).decode("utf-8", errors="replace")
    print(bout)
    b.close()
    ok = "RFQ_TLS_FIXED_PASS" in bout
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
