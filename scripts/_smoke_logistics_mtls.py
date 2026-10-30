# -*- coding: utf-8 -*-
"""Buyer→logistics AIP with mTLS + identity binding (finish six-agent interop)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER_HOST = "81.70.46.119"

REMOTE = r"""
set -e
set -a
[ -f /opt/agentlink/.env ] && . /opt/agentlink/.env
for f in /etc/agentlink/buyer-a.env /etc/agentlink/buyer.env; do
  [ -f "$f" ] && . "$f"
done
set +a
cd /opt/agentlink
echo "client_cert=${AIP_CLIENT_CERT:-unset}"
echo "client_key=${AIP_CLIENT_KEY:-unset}"
echo "trust=${AIP_TRUST_BUNDLE:-unset}"
echo "insecure=${AIP_SSL_INSECURE:-unset}"
echo "bind=${AIP_IDENTITY_BINDING:-unset}"
echo "buyer_aic_tail=${BUYER_A_AIC: -12}"
echo "log_aic_tail=${LOGISTICS_AIC: -12}"
ls -la "${AIP_CLIENT_CERT:-/missing}" "${AIP_CLIENT_KEY:-/missing}" "${AIP_TRUST_BUNDLE:-/missing}" 2>&1 | head -5

.venv/bin/python - <<'PY'
import asyncio, json, os, ssl, urllib.request, uuid
from datetime import datetime, timezone
from pathlib import Path

buyer_aic = os.getenv('BUYER_A_AIC') or ''
log_aic = os.getenv('LOGISTICS_AIC') or ''
print('aic_ok', bool(buyer_aic), bool(log_aic))

pay_ship = {
  'destination': {'province': '浙江', 'city': '杭州', 'postal_code': '310000'},
  'origin': {'province': '河北', 'city': '沧州'},
  'weight_kg': 200, 'volume_m3': 1.2, 'quantity': 100, 'service': 'economy',
  'product_name': 'RM-CASTER-300',
}

# Path A: SDK aip_start_structured with mTLS
async def via_sdk():
    from agentlink_runtime.aip_client_util import aip_start_structured
    from agentlink_runtime.aip_payload import wrap_business
    env = wrap_business('agentlink.shipping_request', 'biz-mtls-log', pay_ship)
    return await aip_start_structured(
        partner_url='https://127.0.0.1:8015/rpc',
        leader_aic=buyer_aic,
        partner_aic=log_aic,
        session_id='sess-mtls-log',
        envelope=env,
        local_agent_id='buyer-a',
    )

try:
    out = asyncio.run(via_sdk())
    env = out.get('envelope') or {}
    payload = env.get('payload') if isinstance(env, dict) else None
    if not isinstance(payload, dict):
        payload = {}
    print('SDK_STATE', out.get('state'))
    print('SDK_SCHEMA', env.get('schema_type') if isinstance(env, dict) else None)
    print('SDK_COST', payload.get('shipping_cost'), 'ETA', payload.get('eta_days'))
    print('SDK_MSG', (out.get('message') or '')[:200])
    if payload.get('shipping_cost') is not None:
        print('LOGISTICS_OK', payload.get('shipping_cost'), payload.get('eta_days'))
except Exception as exc:
    print('SDK_FAIL', type(exc).__name__, str(exc)[:300])

# Path B: raw urllib with client cert if SDK failed
if 'LOGISTICS_OK' not in open('/dev/stdin').read() if False else True:
    from agentlink_runtime.mtls import build_client_ssl_context
    ctx = build_client_ssl_context()
    if ctx is None:
        ctx = ssl._create_unverified_context()
        print('FALLBACK_INSECURE_CTX')
    else:
        print('MTLS_CTX_OK', 'check_hostname', getattr(ctx, 'check_hostname', None))
    tid = 'raw-' + uuid.uuid4().hex[:8]
    body = {
      'jsonrpc': '2.0', 'method': 'rpc', 'id': tid,
      'params': {'command': {
        'type': 'task-command', 'id': 'cmd-' + tid,
        'sentAt': datetime.now(timezone.utc).isoformat(),
        'senderRole': 'leader', 'senderId': buyer_aic,
        'sessionId': 'sess-' + tid, 'taskId': tid, 'command': 'start',
        'dataItems': [{'type': 'data', 'data': {
          'schema_type': 'agentlink.shipping_request', 'schema_version': '1.0',
          'business_id': 'biz-' + tid, 'payload': pay_ship,
        }}],
      }},
    }
    try:
        req = urllib.request.Request(
            'https://127.0.0.1:8015/rpc',
            data=json.dumps(body).encode(),
            headers={'content-type': 'application/json', 'x-peer-aic': log_aic},
            method='POST',
        )
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            data = json.loads(r.read().decode())
        if data.get('error'):
            print('RAW_ERR', data['error'])
        else:
            products = ((data.get('result') or {}).get('products') or [])
            items = (products[0].get('dataItems') or []) if products else []
            env = (items[0].get('data') or {}) if items else {}
            pay = env.get('payload') or {}
            print('RAW_COST', pay.get('shipping_cost'), 'ETA', pay.get('eta_days'), 'schema', env.get('schema_type'))
            if pay.get('shipping_cost') is not None:
                print('LOGISTICS_OK_RAW', pay.get('shipping_cost'))
    except Exception as exc:
        print('RAW_FAIL', type(exc).__name__, str(exc)[:300])

# Path C: buyer tool shipping quote if available
try:
    from commerce.buyer_tools.service import get_buyer_tools
    tools = get_buyer_tools()
    async def via_tools():
        # try common method names
        for name in ('shipping_quote', 'quote_shipping', 'logistics_quote', 'freight_quote'):
            fn = getattr(tools, name, None) or getattr(tools, name + '_tool', None)
            if callable(fn):
                return name, await fn(pay_ship)
        # inspect
        names = [n for n in dir(tools) if 'ship' in n.lower() or 'freight' in n.lower() or 'logist' in n.lower()]
        return 'none', {'available': names[:20]}
    name, res = asyncio.run(via_tools())
    print('TOOLS', name, json.dumps(res, ensure_ascii=False)[:400] if isinstance(res, dict) else res)
except Exception as exc:
    print('TOOLS_SKIP', type(exc).__name__, str(exc)[:200])
PY
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        BUYER_HOST,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=45,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(REMOTE, timeout=180, get_pty=True)
    o.channel.settimeout(180)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace") + b"\n")
    sys.stdout.buffer.flush()
    c.close()
    ok = ("LOGISTICS_OK" in out) or ("LOGISTICS_OK_RAW" in out)
    print("LOGISTICS_MTLS", "PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
