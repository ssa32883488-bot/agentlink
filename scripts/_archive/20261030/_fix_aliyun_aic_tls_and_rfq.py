# -*- coding: utf-8 -*-
"""
Re-issue Aliyun supplier HTTPS certs with CN=AIC (+ IP SAN),
merge into buyer trust-bundle-runtime, keep identity binding, RFQ smoke.
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

ISSUE = r"""
set -e
set -a
. /opt/agentlink/.env
set +a
mkdir -p /etc/agentlink/tls/aic
IP=39.105.20.113

issue_one() {
  local name="$1" aic="$2" port="$3"
  local dir=/etc/agentlink/tls/aic/$name
  mkdir -p "$dir"
  cat > "$dir/openssl.cnf" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req
[dn]
C = CN
O = AgentLink
CN = $aic
[v3_req]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
subjectAltName = @alt
[alt]
IP.1 = $IP
IP.2 = 127.0.0.1
DNS.1 = localhost
URI.1 = acps://$aic
EOF
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -keyout "$dir/server.key" -out "$dir/server.crt" -config "$dir/openssl.cnf"
  chmod 600 "$dir/server.key"
  echo "issued $name CN=$(openssl x509 -in $dir/server.crt -noout -subject)"
  unit=/etc/systemd/system/agentlink-${name}.service
  sed -i "s|^Environment=SSL_CERT=.*|Environment=SSL_CERT=file:${dir}/server.crt|" "$unit"
  sed -i "s|^Environment=SSL_KEY=.*|Environment=SSL_KEY=file:${dir}/server.key|" "$unit"
  grep -E 'SSL_CERT|SSL_KEY' "$unit"
}

issue_one supplier-a "$SUPPLIER_A_AIC" 8011
issue_one supplier-b "$SUPPLIER_B_AIC" 8013
issue_one supplier-c "$SUPPLIER_C_AIC" 8014

systemctl daemon-reload
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 8
for i in 1 2 3 4 5 6 7 8 9 10; do
  a=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8011/health || true)
  b=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8013/health || true)
  c=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8014/health || true)
  echo "health try$i a=$a b=$b c=$c"
  [ "$a$b$c" = 200200200 ] && break
  sleep 2
done
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
python3 - <<'PY'
import ssl, socket, subprocess
from pathlib import Path
ctx=ssl._create_unverified_context()
out=Path('/tmp/aliyun-aic-leaves.pem'); out.write_text('')
for port,name in ((8011,'a'),(8013,'b'),(8014,'c')):
    with ctx.wrap_socket(socket.create_connection(('127.0.0.1',port), timeout=10), server_hostname='127.0.0.1') as s:
        der=s.getpeercert(binary_form=True)
    pem=subprocess.check_output(['openssl','x509','-inform','DER'], input=der)
    open(f'/tmp/leaf-{name}.pem','wb').write(pem)
    print(name, subprocess.check_output(['openssl','x509','-inform','DER','-noout','-subject'], input=der, text=True).strip())
    out.write_bytes(out.read_bytes()+pem if out.stat().st_size else pem)
print('bundle', out.stat().st_size)
PY
echo LEAVES_READY
"""

BUYER = r"""
set -e
BASE=/opt/agentlink/certs/platform
test -f /tmp/aliyun-aic-leaves.pem
cat "$BASE/trust-bundle.pem" /tmp/aliyun-aic-leaves.pem > "$BASE/trust-bundle-runtime.pem"
wc -c "$BASE/trust-bundle-runtime.pem"
# verify each leaf
for n in a b c; do
  openssl x509 -in /tmp/leaf-$n.pem -noout -subject || openssl x509 -in /tmp/aliyun-aic-leaves.pem -noout -subject
done
# split leaves if combined — verify via python extract
python3 - <<'PY'
from pathlib import Path
import subprocess
text=Path('/tmp/aliyun-aic-leaves.pem').read_text()
parts=text.split('-----END CERTIFICATE-----')
leaves=[]
for p in parts:
    p=p.strip()
    if 'BEGIN CERTIFICATE' in p:
        leaves.append(p+'\n-----END CERTIFICATE-----\n')
print('leaves', len(leaves))
ca='/opt/agentlink/certs/platform/trust-bundle-runtime.pem'
for i,leaf in enumerate(leaves):
    Path(f'/tmp/one-{i}.pem').write_text(leaf)
    r=subprocess.run(['openssl','verify','-CAfile',ca,f'/tmp/one-{i}.pem'], capture_output=True, text=True)
    print(i, (r.stdout or r.stderr).strip())
PY

for f in /etc/agentlink/buyer-a.env /etc/agentlink/buyer-b.env; do
  [ -f "$f" ] || continue
  sed -i 's|^AIP_TRUST_BUNDLE=.*|AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem|' "$f"
  grep -q '^AIP_TRUST_BUNDLE=' "$f" || echo 'AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem' >> "$f"
  # keep identity binding ON — certs now carry AIC CN
  sed -i 's|^AIP_IDENTITY_BINDING=.*|AIP_IDENTITY_BINDING=1|' "$f"
  grep -q '^AIP_IDENTITY_BINDING=' "$f" || echo 'AIP_IDENTITY_BINDING=1' >> "$f"
  sed -i 's|^AIP_SSL_INSECURE=.*|AIP_SSL_INSECURE=0|' "$f"
  echo updated $f; grep -E 'AIP_TRUST|AIP_IDENTITY|AIP_SSL_INSECURE' "$f"
done
systemctl restart agentlink-buyer-a
systemctl restart agentlink-buyer-b 2>/dev/null || true
sleep 5
systemctl is-active agentlink-buyer-a

set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, os, urllib.request
from pathlib import Path
for f in ('/opt/agentlink/.env','/etc/agentlink/buyer-a.env'):
    for raw in Path(f).read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1)
        os.environ[k.strip()]=v.strip().strip('"').strip("'")
print('bind', os.getenv('AIP_IDENTITY_BINDING'), 'trust', os.getenv('AIP_TRUST_BUNDLE'))
from agentlink_runtime.mtls import build_client_ssl_context
ctx=build_client_ssl_context()
with urllib.request.urlopen(urllib.request.Request('https://39.105.20.113:8011/health'), context=ctx, timeout=20) as r:
    print('health_verified', r.status)

from commerce.buyer_tools.service import get_buyer_tools
async def main():
    tools=get_buyer_tools()
    disc=await tools.discover_suppliers_tool({'product_name':'重型脚轮','quantity':500,'query':'脚轮 供应商','limit':5,'refresh':True})
    print('discover', disc.get('source'), 'n', len(disc.get('candidates') or []), 'case', disc.get('case_id'))
    selected=[c.get('candidate_id') for c in (disc.get('candidates') or [])[:3] if c.get('candidate_id')] or ['supplier-a','supplier-b','supplier-c']
    out=await tools.rfq_send_batch({'case_id': disc.get('case_id'), 'selected': selected})
    rows=[]; ok_n=0
    for q in out.get('quotes') or []:
        p=q.get('partner') or {}; fr=q.get('freight') or {}
        goods=q.get('goods_total'); err=q.get('error') or ''
        if goods is not None: ok_n += 1
        rows.append({'name': p.get('name') or p.get('agent_id'), 'status': q.get('status'), 'goods': goods,
                     'freight': fr.get('amount') if isinstance(fr, dict) else q.get('freight_amount'),
                     'grand': q.get('grand_total'), 'lead': q.get('lead_time_days') or q.get('lead_days'), 'err': err[:160]})
    print(json.dumps({'ok': out.get('ok'), 'summary': out.get('summary'), 'rows': rows}, ensure_ascii=False))
    print('RFQ_OK_COUNT', ok_n)
    print('RFQ_TLS_FIXED_PASS' if ok_n >= 3 else 'RFQ_TLS_FIXED_PARTIAL')
asyncio.run(main())
PY
"""


def main() -> int:
    print("==== issue AIC TLS on Aliyun ====", flush=True)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ALIYUN, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(ISSUE, timeout=180, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out)
    if "LEAVES_READY" not in out:
        c.close()
        return 1
    sftp = c.open_sftp()
    files = {
        "/tmp/aliyun-aic-leaves.pem": None,
        "/tmp/leaf-a.pem": None,
        "/tmp/leaf-b.pem": None,
        "/tmp/leaf-c.pem": None,
    }
    payloads = {}
    for remote in files:
        with sftp.file(remote, "r") as f:
            data = f.read()
            payloads[remote] = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
    sftp.close()
    c.close()

    print("==== buyer merge + RFQ ====", flush=True)
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
    for remote, content in payloads.items():
        with sftp.file(remote, "w") as f:
            f.write(content)
    sftp.close()
    _, o2, e2 = b.exec_command(BUYER, timeout=300, get_pty=True)
    o2.channel.settimeout(300)
    bout = (o2.read() + e2.read()).decode("utf-8", errors="replace")
    print(bout)
    b.close()
    ok = "RFQ_TLS_FIXED_PASS" in bout
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
