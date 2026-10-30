# -*- coding: utf-8 -*-
"""After AIC cert reissue: wait Java health, merge buyer trust, smoke RFQ."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
ALIYUN = "39.105.20.113"
TENCENT = "81.70.46.119"

WAIT_AND_LEAVES = r"""
set -e
for i in $(seq 1 30); do
  a=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8011/health || true)
  b=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8013/health || true)
  c=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8014/health || true)
  echo "try$i a=$a b=$b c=$c"
  [ "$a$b$c" = 200200200 ] && break
  sleep 5
done
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for p in 8011 8013 8014; do
  echo -n "H:$p "
  curl -sk https://127.0.0.1:$p/health; echo
  echo | timeout 5 openssl s_client -connect 127.0.0.1:$p 2>/dev/null | openssl x509 -noout -subject
done
python3 - <<'PY'
import ssl, socket, subprocess
from pathlib import Path
ctx=ssl._create_unverified_context()
out=Path('/tmp/aliyun-aic-leaves.pem'); out.write_bytes(b'')
for port,name in ((8011,'a'),(8013,'b'),(8014,'c')):
    with ctx.wrap_socket(socket.create_connection(('127.0.0.1',port), timeout=10), server_hostname='127.0.0.1') as s:
        der=s.getpeercert(binary_form=True)
    pem=subprocess.check_output(['openssl','x509','-inform','DER'], input=der)
    open('/tmp/leaf-%s.pem' % name,'wb').write(pem)
    subj=subprocess.check_output(['openssl','x509','-inform','DER','-noout','-subject'], input=der).decode('utf-8','replace').strip()
    print(name, subj)
    out.write_bytes(out.read_bytes()+pem)
print('bundle', out.stat().st_size)
PY
echo LEAVES_READY
"""

BUYER = r"""
set -e
BASE=/opt/agentlink/certs/platform
cat "$BASE/trust-bundle.pem" /tmp/aliyun-aic-leaves.pem > "$BASE/trust-bundle-runtime.pem"
wc -c "$BASE/trust-bundle-runtime.pem"
for f in /etc/agentlink/buyer-a.env /etc/agentlink/buyer-b.env /opt/agentlink/.env; do
  [ -f "$f" ] || continue
  sed -i 's|^AIP_TRUST_BUNDLE=.*|AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem|' "$f"
  grep -q '^AIP_TRUST_BUNDLE=' "$f" || echo 'AIP_TRUST_BUNDLE=/opt/agentlink/certs/platform/trust-bundle-runtime.pem' >> "$f"
  sed -i 's|^AIP_IDENTITY_BINDING=.*|AIP_IDENTITY_BINDING=1|' "$f"
  grep -q '^AIP_IDENTITY_BINDING=' "$f" || echo 'AIP_IDENTITY_BINDING=1' >> "$f"
  sed -i 's|^AIP_SSL_INSECURE=.*|AIP_SSL_INSECURE=0|' "$f"
  echo updated $f
  grep -E 'AIP_TRUST|AIP_IDENTITY|AIP_SSL_INSECURE' "$f" || true
done
systemctl restart agentlink-buyer-a agentlink-buyer-b
sleep 8
systemctl is-active agentlink-buyer-a agentlink-buyer-b
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, os
from pathlib import Path
for f in ('/opt/agentlink/.env','/etc/agentlink/buyer-a.env'):
    for raw in Path(f).read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1)
        os.environ[k.strip()]=v.strip().strip('"').strip("'")
print('bind', os.getenv('AIP_IDENTITY_BINDING'), 'trust', os.getenv('AIP_TRUST_BUNDLE'))
from commerce.buyer_tools.service import get_buyer_tools
async def main():
    tools=get_buyer_tools()
    disc=await tools.discover_suppliers_tool({'product_name':'高档座椅面料','quantity':300,'query':'座椅面料 供应商','limit':5,'refresh':True})
    print('discover', disc.get('source'), 'n', len(disc.get('candidates') or []), 'case', disc.get('case_id'), 'err', disc.get('platform_error'))
    selected=[c.get('candidate_id') for c in (disc.get('candidates') or [])[:3] if c.get('candidate_id')]
    if len(selected)<3:
        selected=['supplier-a','supplier-b','supplier-c']
    out=await tools.rfq_send_batch({'case_id': disc.get('case_id'), 'selected': selected})
    rows=[]; ok_n=0
    for q in out.get('quotes') or []:
        p=q.get('partner') or {}; fr=q.get('freight') or {}
        goods=q.get('goods_total'); err=q.get('error') or ''
        if goods is not None: ok_n += 1
        rows.append({'name': p.get('name') or p.get('agent_id'), 'status': q.get('status'), 'goods': goods,
                     'freight': fr.get('amount') if isinstance(fr, dict) else q.get('freight_amount'),
                     'grand': q.get('grand_total'), 'err': str(err)[:200]})
    print(json.dumps({'ok': out.get('ok'), 'summary': out.get('summary'), 'rows': rows}, ensure_ascii=False, indent=2))
    print('RFQ_OK_COUNT', ok_n)
    print('RFQ_TLS_FIXED_PASS' if ok_n >= 3 else 'RFQ_TLS_FIXED_PARTIAL')
asyncio.run(main())
PY
"""


def main() -> int:
    print("==== wait Aliyun + leaves ====", flush=True)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ALIYUN, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(WAIT_AND_LEAVES, timeout=240, get_pty=True)
    o.channel.settimeout(240)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out, flush=True)
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
    _, o2, e2 = b.exec_command(BUYER, timeout=360, get_pty=True)
    o2.channel.settimeout(360)
    bout = (o2.read() + e2.read()).decode("utf-8", errors="replace")
    print(bout, flush=True)
    b.close()
    ok = "RFQ_TLS_FIXED_PASS" in bout
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
