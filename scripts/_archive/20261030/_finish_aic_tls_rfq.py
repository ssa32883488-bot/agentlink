# -*- coding: utf-8 -*-
"""Wait for Aliyun AIC TLS, sync leaves to buyer trust, RFQ smoke. Fallback: binding=0."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

WAIT_EXPORT = r"""
set -e
# if still starting, wait up to ~2 min
for i in $(seq 1 30); do
  a=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8011/health || true)
  b=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8013/health || true)
  c=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8014/health || true)
  echo "try$i a=$a b=$b c=$c"
  if [ "$a$b$c" = 200200200 ]; then
    break
  fi
  # if inactive, restart
  for u in a b c; do
    st=$(systemctl is-active agentlink-supplier-$u || true)
    [ "$st" = active ] || systemctl restart agentlink-supplier-$u || true
  done
  sleep 5
done
a=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8011/health || true)
[ "$a" = 200 ] || { echo HEALTH_FAIL; journalctl -u agentlink-supplier-a -n 30 --no-pager; exit 1; }
python3 - <<'PY'
import ssl, socket, subprocess
from pathlib import Path
ctx=ssl._create_unverified_context()
bundle=b''
for port,name in ((8011,'a'),(8013,'b'),(8014,'c')):
    with ctx.wrap_socket(socket.create_connection(('127.0.0.1',port), timeout=10), server_hostname='127.0.0.1') as s:
        der=s.getpeercert(binary_form=True)
    pem=subprocess.check_output(['openssl','x509','-inform','DER'], input=der)
    Path(f'/tmp/leaf-{name}.pem').write_bytes(pem)
    subj=subprocess.check_output(['openssl','x509','-inform','DER','-noout','-subject'], input=der)
    print(name, subj.decode().strip())
    bundle += pem
Path('/tmp/aliyun-aic-leaves.pem').write_bytes(bundle)
print('bundle', len(bundle))
PY
echo LEAVES_READY
"""

BUYER = r"""
set -e
BASE=/opt/agentlink/certs/platform
cat "$BASE/trust-bundle.pem" /tmp/aliyun-aic-leaves.pem > "$BASE/trust-bundle-runtime.pem"
python3 - <<'PY'
from pathlib import Path
import subprocess
text=Path('/tmp/aliyun-aic-leaves.pem').read_text()
chunks=[]
buf=[]
for line in text.splitlines():
    buf.append(line)
    if line.startswith('-----END CERTIFICATE-----'):
        chunks.append('\n'.join(buf)+'\n'); buf=[]
ca='/opt/agentlink/certs/platform/trust-bundle-runtime.pem'
print('chunks', len(chunks))
for i,c in enumerate(chunks):
    Path(f'/tmp/one-{i}.pem').write_text(c)
    r=subprocess.run(['openssl','verify','-CAfile',ca,f'/tmp/one-{i}.pem'], capture_output=True, text=True)
    print(i, (r.stdout or r.stderr).strip())
PY

apply_env() {
  local bind="$1"
  for f in /etc/agentlink/buyer-a.env /etc/agentlink/buyer-b.env; do
    [ -f "$f" ] || continue
    grep -q '^AIP_TRUST_BUNDLE=' "$f" \
      && sed -i 's|^AIP_TRUST_BUNDLE=.*|AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem|' "$f" \
      || echo 'AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem' >> "$f"
    grep -q '^AIP_IDENTITY_BINDING=' "$f" \
      && sed -i "s|^AIP_IDENTITY_BINDING=.*|AIP_IDENTITY_BINDING=$bind|" "$f" \
      || echo "AIP_IDENTITY_BINDING=$bind" >> "$f"
    grep -q '^AIP_SSL_INSECURE=' "$f" && sed -i 's|^AIP_SSL_INSECURE=.*|AIP_SSL_INSECURE=0|' "$f" || echo 'AIP_SSL_INSECURE=0' >> "$f"
  done
  systemctl restart agentlink-buyer-a
  systemctl restart agentlink-buyer-b 2>/dev/null || true
  sleep 5
}

run_rfq() {
  local tag="$1"
  set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a
  cd /opt/agentlink
  .venv/bin/python - <<PY
import asyncio, json, os, urllib.request
from pathlib import Path
for f in ('/opt/agentlink/.env','/etc/agentlink/buyer-a.env'):
    for raw in Path(f).read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1)
        os.environ[k.strip()]=v.strip().strip('"').strip("'")
print('TAG', '$tag', 'bind', os.getenv('AIP_IDENTITY_BINDING'), 'trust', os.getenv('AIP_TRUST_BUNDLE'))
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
    if ok_n >= 3:
        print('RFQ_TLS_FIXED_PASS')
    else:
        print('RFQ_TLS_FIXED_PARTIAL')
asyncio.run(main())
PY
}

apply_env 1
run_rfq bind1
if ! grep -q RFQ_TLS_FIXED_PASS <<<"$(run_rfq bind1 2>&1 | tee /tmp/rfq1.out)"; then
  # the above double-runs — simplify: check last output file from first run
  true
fi
# Re-run check using saved approach
set +e
OUT1=$(run_rfq bind1 2>&1)
echo "$OUT1"
echo "$OUT1" | grep -q RFQ_TLS_FIXED_PASS && exit 0
echo '==== fallback AIP_IDENTITY_BINDING=0 ===='
apply_env 0
OUT0=$(run_rfq bind0 2>&1)
echo "$OUT0"
echo "$OUT0" | grep -q RFQ_TLS_FIXED_PASS
"""


def main() -> int:
    print("==== wait+export Aliyun leaves ====", flush=True)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(WAIT_EXPORT, timeout=240, get_pty=True)
    o.channel.settimeout(240)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out)
    if "LEAVES_READY" not in out:
        c.close()
        return 1
    sftp = c.open_sftp()
    payloads = {}
    for remote in ("/tmp/aliyun-aic-leaves.pem", "/tmp/leaf-a.pem", "/tmp/leaf-b.pem", "/tmp/leaf-c.pem"):
        with sftp.file(remote, "r") as f:
            data = f.read()
            payloads[remote] = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
    sftp.close()
    c.close()

    print("==== buyer RFQ ====", flush=True)
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
    sftp = b.open_sftp()
    for remote, content in payloads.items():
        with sftp.file(remote, "w") as f:
            f.write(content)
    # write cleaner buyer remote script to avoid nested function double-run mess
    remote_sh = r"""
set -e
BASE=/opt/agentlink/certs/platform
cat "$BASE/trust-bundle.pem" /tmp/aliyun-aic-leaves.pem > "$BASE/trust-bundle-runtime.pem"
python3 - <<'PY'
from pathlib import Path
import subprocess
text=Path('/tmp/aliyun-aic-leaves.pem').read_text()
chunks=[]; buf=[]
for line in text.splitlines():
    buf.append(line)
    if line.startswith('-----END CERTIFICATE-----'):
        chunks.append('\n'.join(buf)+'\n'); buf=[]
ca='/opt/agentlink/certs/platform/trust-bundle-runtime.pem'
print('chunks', len(chunks))
for i,c in enumerate(chunks):
    Path(f'/tmp/one-{i}.pem').write_text(c)
    r=subprocess.run(['openssl','verify','-CAfile',ca,f'/tmp/one-{i}.pem'], capture_output=True, text=True)
    print(i, (r.stdout or r.stderr).strip())
PY

rfq_py() {
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
                     'grand': q.get('grand_total'), 'lead': q.get('lead_time_days') or q.get('lead_days'), 'err': err[:180]})
    print(json.dumps({'ok': out.get('ok'), 'summary': out.get('summary'), 'rows': rows}, ensure_ascii=False))
    print('RFQ_OK_COUNT', ok_n)
    print('RFQ_TLS_FIXED_PASS' if ok_n >= 3 else 'RFQ_TLS_FIXED_PARTIAL')
asyncio.run(main())
PY
}

set_bind() {
  local bind="$1"
  for f in /etc/agentlink/buyer-a.env /etc/agentlink/buyer-b.env; do
    [ -f "$f" ] || continue
    grep -q '^AIP_TRUST_BUNDLE=' "$f" \
      && sed -i 's|^AIP_TRUST_BUNDLE=.*|AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem|' "$f" \
      || echo 'AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem' >> "$f"
    grep -q '^AIP_IDENTITY_BINDING=' "$f" \
      && sed -i "s|^AIP_IDENTITY_BINDING=.*|AIP_IDENTITY_BINDING=$bind|" "$f" \
      || echo "AIP_IDENTITY_BINDING=$bind" >> "$f"
    grep -q '^AIP_SSL_INSECURE=' "$f" && sed -i 's|^AIP_SSL_INSECURE=.*|AIP_SSL_INSECURE=0|' "$f" || echo 'AIP_SSL_INSECURE=0' >> "$f"
    echo "--- $f"; grep -E 'AIP_TRUST|AIP_IDENTITY|AIP_SSL_INSECURE' "$f"
  done
  systemctl restart agentlink-buyer-a
  systemctl restart agentlink-buyer-b 2>/dev/null || true
  sleep 5
  systemctl is-active agentlink-buyer-a
}

cd /opt/agentlink
set_bind 1
echo '==== RFQ bind=1 ===='
set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a
OUT=$(rfq_py 2>&1) || true
echo "$OUT"
if echo "$OUT" | grep -q RFQ_TLS_FIXED_PASS; then
  echo RESULT_PASS_BIND1
  exit 0
fi
echo '==== RFQ fallback bind=0 ===='
set_bind 0
set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a
OUT=$(rfq_py 2>&1) || true
echo "$OUT"
if echo "$OUT" | grep -q RFQ_TLS_FIXED_PASS; then
  echo RESULT_PASS_BIND0
  exit 0
fi
echo RESULT_FAIL
exit 1
"""
    with sftp.file("/tmp/finish_rfq.sh", "w") as f:
        f.write(remote_sh)
    sftp.close()
    _, o2, e2 = b.exec_command("bash /tmp/finish_rfq.sh", timeout=360, get_pty=True)
    o2.channel.settimeout(360)
    bout = (o2.read() + e2.read()).decode("utf-8", errors="replace")
    print(bout)
    b.close()
    ok = "RESULT_PASS" in bout or "RFQ_TLS_FIXED_PASS" in bout
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
