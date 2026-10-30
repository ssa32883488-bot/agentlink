# -*- coding: utf-8 -*-
"""
Buyer RFQ TLS fix:
1) Try switching Aliyun Java SSL to platform server PEMs (trusted by Agent CA).
2) If Java cannot serve those (often Ed25519), keep self-signed and append
   Aliyun leaf cert into buyer's AIP trust bundle so RFQ verifies.
3) Smoke rfq_send_batch from Tencent buyer-a.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
ALIYUN = "39.105.20.113"
TENCENT = "81.70.46.119"

TRY_PLATFORM = r"""
set -e
backup_units() {
  for u in a b c; do
    cp -a /etc/systemd/system/agentlink-supplier-${u}.service /tmp/agentlink-supplier-${u}.service.bak
  done
}
backup_units
for u in a b c; do
  unit=/etc/systemd/system/agentlink-supplier-${u}.service
  cert=/opt/agentlink/certs/platform/supplier-${u}/server-cert.pem
  key=/opt/agentlink/certs/platform/supplier-${u}/server-key.pem
  sed -i "s|^Environment=SSL_CERT=.*|Environment=SSL_CERT=file:${cert}|" "$unit"
  sed -i "s|^Environment=SSL_KEY=.*|Environment=SSL_KEY=file:${key}|" "$unit"
done
systemctl daemon-reload
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c || true
sleep 7
ok=1
for u in a b c; do
  st=$(systemctl is-active agentlink-supplier-$u || true)
  echo "state_$u=$st"
  [ "$st" = active ] || ok=0
done
code=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8011/health || true)
echo "health_a=$code"
subj=$(echo | timeout 5 openssl s_client -connect 127.0.0.1:8011 2>/dev/null | openssl x509 -noout -subject 2>/dev/null || true)
echo "subject=$subj"
if [ "$ok" = 1 ] && [ "$code" = 200 ]; then
  echo 'PLATFORM_TLS_OK'
  echo | timeout 5 openssl s_client -connect 127.0.0.1:8011 -showcerts 2>/dev/null | openssl x509 > /tmp/presented-a.pem || true
  openssl verify -CAfile /opt/agentlink/certs/platform/trust-bundle.pem /tmp/presented-a.pem || true
else
  echo 'PLATFORM_TLS_FAIL_REVERT'
  for u in a b c; do
    cp -a /tmp/agentlink-supplier-${u}.service.bak /etc/systemd/system/agentlink-supplier-${u}.service
  done
  systemctl daemon-reload
  systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
  sleep 6
  systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
  # export current self-signed leaf for buyer trust merge
  echo | timeout 5 openssl s_client -connect 127.0.0.1:8011 -showcerts 2>/dev/null | openssl x509 > /tmp/aliyun-selfsigned.pem
  wc -c /tmp/aliyun-selfsigned.pem
  echo 'SELFSIGNED_EXPORT_READY'
fi
"""

EXPORT_CERT = r"""
set -e
echo | timeout 6 openssl s_client -connect 127.0.0.1:8011 -showcerts 2>/dev/null | openssl x509
"""

MERGE_AND_SMOKE = r"""
set -e
set -a
. /opt/agentlink/.env
. /etc/agentlink/buyer-a.env
set +a
BASE=/opt/agentlink/certs/platform
mkdir -p "$BASE"
# merge trust: platform + aliyun leaf (+ keep previous merge if any)
cat "$BASE/trust-bundle.pem" /tmp/aliyun-selfsigned.pem > "$BASE/trust-bundle-with-aliyun.pem"
# also append same leaf for b/c if identical issuer (same file is fine)
cp -f "$BASE/trust-bundle-with-aliyun.pem" "$BASE/trust-bundle-runtime.pem"
# point buyer-a (+ buyer-b if present) env at runtime trust
for f in /etc/agentlink/buyer-a.env /etc/agentlink/buyer-b.env; do
  [ -f "$f" ] || continue
  if grep -q '^AIP_TRUST_BUNDLE=' "$f"; then
    sed -i 's|^AIP_TRUST_BUNDLE=.*|AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem|' "$f"
  else
    echo 'AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem' >> "$f"
  fi
  # keep verification on
  grep -q '^AIP_SSL_INSECURE=' "$f" && sed -i 's|^AIP_SSL_INSECURE=.*|AIP_SSL_INSECURE=0|' "$f" || echo 'AIP_SSL_INSECURE=0' >> "$f"
  echo "--- $f ---"; grep -E 'AIP_TRUST|AIP_SSL_INSECURE' "$f"
done
# verify openssl
openssl verify -CAfile /opt/agentlink/certs/platform/trust-bundle-runtime.pem /tmp/aliyun-selfsigned.pem || true
# restart buyers so systemd reloads EnvironmentFile
systemctl restart agentlink-buyer-a agentlink-buyer-b 2>/dev/null || systemctl restart agentlink-buyer-a
sleep 4
systemctl is-active agentlink-buyer-a || true

cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, os, ssl, urllib.request
from pathlib import Path

# confirm process env would see trust after restart — smoke uses explicit load like systemd
os.environ['AIP_TRUST_BUNDLE'] = '/opt/agentlink/certs/platform/trust-bundle-runtime.pem'
os.environ['AIP_SSL_INSECURE'] = '0'
# reload client certs from buyer-a.env
for raw in Path('/etc/agentlink/buyer-a.env').read_text(encoding='utf-8').splitlines():
    line=raw.strip()
    if not line or line.startswith('#') or '=' not in line: continue
    k,v=line.split('=',1)
    os.environ[k.strip()] = v.strip().strip('"').strip("'")

from agentlink_runtime.mtls import build_client_ssl_context
ctx = build_client_ssl_context()
print('ctx_ok', bool(ctx), 'verify', getattr(ctx,'verify_mode',None))
# raw https health with ctx
req=urllib.request.Request('https://39.105.20.113:8011/health')
try:
    with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
        print('health_verified', r.status, r.read()[:120])
except Exception as e:
    print('health_verified_FAIL', type(e).__name__, str(e)[:200])

from commerce.buyer_tools.service import get_buyer_tools

async def main():
    tools = get_buyer_tools()
    disc = await tools.discover_suppliers_tool({
        'product_name': '重型脚轮', 'quantity': 500, 'query': '脚轮 供应商', 'limit': 5, 'refresh': True,
    })
    print('discover', disc.get('source'), 'n', len(disc.get('candidates') or []), 'case', disc.get('case_id'))
    cands = disc.get('candidates') or []
    selected = [c.get('candidate_id') for c in cands[:3] if c.get('candidate_id')] or ['supplier-a','supplier-b','supplier-c']
    out = await tools.rfq_send_batch({'case_id': disc.get('case_id'), 'selected': selected})
    rows=[]
    ok_n=0
    for q in out.get('quotes') or []:
        p=q.get('partner') or {}
        fr=q.get('freight') or {}
        goods=q.get('goods_total')
        status=q.get('status')
        err=(q.get('error') or '')
        if goods is not None and 'certificate' not in err.lower() and 'SSL' not in err and '证书' not in err:
            ok_n += 1
        rows.append({
            'name': p.get('name') or p.get('agent_id'),
            'status': status,
            'goods': goods,
            'freight': fr.get('amount') if isinstance(fr, dict) else q.get('freight_amount'),
            'grand': q.get('grand_total'),
            'lead': q.get('lead_time_days') or q.get('lead_days'),
            'err': err[:160],
        })
    print(json.dumps({'ok': out.get('ok'), 'summary': out.get('summary'), 'rows': rows}, ensure_ascii=False))
    print('RFQ_OK_COUNT', ok_n)
    print('RFQ_TLS_FIXED_PASS' if ok_n >= 3 else 'RFQ_TLS_FIXED_PARTIAL')

asyncio.run(main())
PY
"""


def ssh_pw(cmd: str, timeout: int = 180) -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ALIYUN, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    c.close()
    return out


def ssh_pem(cmd: str, timeout: int = 240) -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        TENCENT,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    c.close()
    return out


def main() -> int:
    print("==== 1) try platform TLS on Aliyun ====", flush=True)
    out1 = ssh_pw(TRY_PLATFORM, timeout=180)
    print(out1)
    platform_ok = "PLATFORM_TLS_OK" in out1

    print("==== 2) fetch presented leaf for buyer trust ====", flush=True)
    leaf = ssh_pw(EXPORT_CERT, timeout=30)
    if "BEGIN CERTIFICATE" not in leaf:
        print("NO_LEAF", leaf[:500], flush=True)
        return 1
    # upload leaf to tencent via nested ssh from local: write temp + scp-like through paramiko
    print("leaf_bytes", len(leaf), "platform_ok", platform_ok, flush=True)

    print("==== 3) merge trust on buyer + RFQ smoke ====", flush=True)
    # put leaf on tencent
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        TENCENT,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = c.open_sftp()
    with sftp.file("/tmp/aliyun-selfsigned.pem", "w") as f:
        # keep only cert block
        start = leaf.find("-----BEGIN CERTIFICATE-----")
        end = leaf.find("-----END CERTIFICATE-----")
        block = leaf[start : end + len("-----END CERTIFICATE-----")] + "\n"
        f.write(block)
    sftp.close()
    _, o, e = c.exec_command(MERGE_AND_SMOKE, timeout=300, get_pty=True)
    o.channel.settimeout(300)
    bout = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(bout)
    c.close()

    ok = "RFQ_TLS_FIXED_PASS" in bout
    print("RESULT", "PASS" if ok else "FAIL", "platform_tls", platform_ok, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
