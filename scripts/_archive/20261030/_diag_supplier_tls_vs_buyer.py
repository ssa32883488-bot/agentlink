# -*- coding: utf-8 -*-
"""Compare Aliyun supplier server cert vs buyer trust-bundle; probe AIP with buyer mTLS."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def ssh(host: str, cmd: str, timeout: int = 90) -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        host,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    c.close()
    return out


def main() -> None:
    print("===== ALIYUN suppliers TLS =====")
    print(
        ssh(
            "39.105.20.113",
            r"""
set +e
for p in 8011 8013 8014; do
  echo "--- :$p ---"
  echo | timeout 6 openssl s_client -connect 127.0.0.1:$p 2>/dev/null | openssl x509 -noout -subject -issuer -fingerprint -sha256 2>/dev/null
done
echo '=== java unit Environment TLS ==='
systemctl cat agentlink-supplier-a 2>/dev/null | grep -E 'Environment|CERT|KEY|TLS|JAVA' | head -30
ls -la /opt/agentlink/certs/platform/supplier-a/ 2>/dev/null | head
ls -la /etc/agentlink/tls/ 2>/dev/null | head
ls -la /opt/agentlink/certs/ 2>/dev/null | head -20
""",
        )
    )

    print("===== TENCENT buyer trust + live RFQ probe =====")
    print(
        ssh(
            "81.70.46.119",
            r"""
set -a
. /opt/agentlink/.env
. /etc/agentlink/buyer-a.env
set +a
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, os, ssl, subprocess
from pathlib import Path

print('TRUST', os.getenv('AIP_TRUST_BUNDLE'))
print('CLIENT', os.getenv('AIP_CLIENT_CERT'))
print('INSECURE', os.getenv('AIP_SSL_INSECURE'))

# Does trust-bundle verify supplier cert?
import tempfile
pem = subprocess.check_output(['bash','-lc','echo | openssl s_client -connect 39.105.20.113:8011 -showcerts 2>/dev/null | openssl x509'], text=True)
tp = Path('/tmp/sup-a.pem'); tp.write_text(pem)
ca = os.getenv('AIP_TRUST_BUNDLE')
r = subprocess.run(['openssl','verify','-CAfile',ca,str(tp)], capture_output=True, text=True)
print('openssl_verify', r.stdout.strip() or r.stderr.strip())

from agentlink_runtime.mtls import build_client_ssl_context
from agentlink_runtime.aip_client_util import aip_start_structured
from agentlink_runtime.aip_payload import wrap_business

ctx = build_client_ssl_context()
print('ctx', bool(ctx), 'verify_mode', getattr(ctx,'verify_mode',None))

buyer=os.getenv('BUYER_A_AIC')
sa=os.getenv('SUPPLIER_A_AIC') or buyer
payload={
  'purchase_request_id':'pr-tls-fix','quantity':100,'product_name':'RM-CASTER-300','sku':'RM-CASTER-300',
  'specifications':{'sku':'RM-CASTER-300'},
  'destination':{'province':'浙江','city':'杭州','postal_code':'310000'},'need_freight':False,
}
async def go(url, partner):
    env=wrap_business('agentlink.quote_request','biz-tls', payload)
    return await aip_start_structured(partner_url=url, leader_aic=buyer, partner_aic=partner, session_id='sess-tls', envelope=env, local_agent_id='buyer-a')

try:
    out=asyncio.run(go('https://39.105.20.113:8011/rpc', sa))
    env=out.get('envelope') or {}
    pay=(env.get('payload') or {}) if isinstance(env, dict) else {}
    print('MTLS_QUOTE', out.get('state'), pay.get('unit_price'), (out.get('message') or '')[:160])
except Exception as e:
    print('MTLS_QUOTE_FAIL', type(e).__name__, str(e)[:300])

# insecure fallback probe
os.environ['AIP_SSL_INSECURE']='1'
# clear certs so build uses insecure path? Actually build prefers cert+ca first.
# Temporarily rename env
for k in ('AIP_CLIENT_CERT','AIP_CLIENT_KEY','AIP_TRUST_BUNDLE'):
    os.environ.pop(k, None)
os.environ['AIP_SSL_INSECURE']='1'
try:
    out=asyncio.run(go('https://39.105.20.113:8011/rpc', sa or 'x'))
    env=out.get('envelope') or {}
    pay=(env.get('payload') or {}) if isinstance(env, dict) else {}
    print('INSECURE_QUOTE', out.get('state'), pay.get('unit_price'))
except Exception as e:
    print('INSECURE_QUOTE_FAIL', type(e).__name__, str(e)[:300])
PY
""",
            timeout=120,
        )
    )


if __name__ == "__main__":
    main()
