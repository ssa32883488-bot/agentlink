# -*- coding: utf-8 -*-
"""Finish six-agent interop: proper AIC logistics quote + buyer→supplier already known OK."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER_HOST = "81.70.46.119"

REMOTE = r"""
set -e
cd /opt/agentlink
echo '=== env snippet ==='
grep -E '^(AIP_IDENTITY_BINDING|LOGISTICS_AIC|BUYER_A_AIC)=' .env | sed 's/\(AIC=\).*/\1***/'
systemctl cat agentlink-logistics 2>/dev/null | grep -E 'Environment=|ExecStart=' | head -20 || true
curl -sk https://127.0.0.1:8015/health; echo

.venv/bin/python - <<'PY'
import json, os, ssl, urllib.request, uuid
from datetime import datetime, timezone
from pathlib import Path

# load .env
for raw in Path('/opt/agentlink/.env').read_text(encoding='utf-8').splitlines():
    line=raw.strip()
    if not line or line.startswith('#') or '=' not in line: continue
    k,v=line.split('=',1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

ctx=ssl._create_unverified_context()
buyer_aic=os.getenv('BUYER_A_AIC') or '1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW'
log_aic=os.getenv('LOGISTICS_AIC') or '1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS'
print('buyer_aic_tail', buyer_aic[-12:], 'log_aic_tail', log_aic[-12:], 'bind', os.getenv('AIP_IDENTITY_BINDING'))

def now():
    return datetime.now(timezone.utc).isoformat()

def rpc(url, schema, payload, sender_id, peer_hint=None):
    tid='fin-'+uuid.uuid4().hex[:8]
    envelope={'schema_type':schema,'schema_version':'1.0','business_id':'biz-'+tid,'payload':payload}
    # acps task command may carry peer via senderId; some servers want X headers — stick to body
    body={
      'jsonrpc':'2.0','method':'rpc','id':tid,
      'params':{'command':{
        'type':'task-command','id':'cmd-'+tid,'sentAt':now(),
        'senderRole':'leader','senderId':sender_id,
        'sessionId':'sess-'+tid,'taskId':tid,'command':'start',
        'dataItems':[{'type':'data','data':envelope}],
      }}
    }
    req=urllib.request.Request(url, data=json.dumps(body).encode(), headers={'content-type':'application/json'}, method='POST')
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return json.loads(r.read().decode())

def payload_of(data):
    err=data.get('error')
    if err:
        return {'_error': err}
    res=data.get('result') or {}
    products=res.get('products') or []
    if not products:
        st=(res.get('status') or {})
        return {'_state': st.get('state') if isinstance(st, dict) else st, '_result_keys': list(res.keys())}
    items=products[0].get('dataItems') or []
    if not items:
        return {}
    env=items[0].get('data') or {}
    return env.get('payload') or {'_schema': env.get('schema_type')}

# 1) logistics with real AIC sender
pay_ship={
  'destination':{'province':'浙江','city':'杭州','postal_code':'310000'},
  'origin':{'province':'河北','city':'沧州'},
  'weight_kg':200,'volume_m3':1.2,'quantity':100,'service':'economy',
  'product_name':'RM-CASTER-300',
}
for schema in ('agentlink.shipping_request','agentlink.shipping_quote_request'):
    data=rpc('https://127.0.0.1:8015/rpc', schema, pay_ship, buyer_aic)
    pay=payload_of(data)
    print('LOGISTICS', schema, '=>', {k:pay.get(k) for k in ('shipping_cost','eta_days','_error','_state') if k in pay or pay.get(k) is not None})
    if pay.get('shipping_cost') is not None:
        print('LOGISTICS_OK', pay.get('shipping_cost'), pay.get('eta_days'))
        break
else:
    # try via SDK if available
    try:
        import asyncio
        from agentlink_runtime.aip_client_util import aip_start_structured
        from agentlink_runtime.aip_payload import wrap_business
        async def go():
            env=wrap_business('agentlink.shipping_request','biz-sdk', pay_ship)
            return await aip_start_structured(
                partner_url='https://127.0.0.1:8015/rpc',
                leader_aic=buyer_aic,
                partner_aic=log_aic,
                session_id='sess-sdk-log',
                envelope=env,
                local_agent_id='buyer-a',
            )
        out=asyncio.get_event_loop().run_until_complete(go())
        print('LOGISTICS_SDK', out.get('state'), (out.get('envelope') or {}).get('schema_type'), ((out.get('envelope') or {}).get('payload') or {}).get('shipping_cost'))
        if ((out.get('envelope') or {}).get('payload') or {}).get('shipping_cost') is not None:
            print('LOGISTICS_OK_SDK')
    except Exception as exc:
        print('LOGISTICS_SDK_FAIL', exc)

# 2) reconfirm buyer→3 suppliers from this host
ok_sup=True
for agent,url,sku,qty in (
 ('supplier-a','https://39.105.20.113:8011/rpc','RM-CASTER-300',100),
 ('supplier-b','https://39.105.20.113:8013/rpc','RM-FABRIC-PRO',50),
 ('supplier-c','https://39.105.20.113:8014/rpc','RM-TUBE-STEEL',20),
):
    data=rpc(url,'agentlink.quote_request',{
      'purchase_request_id':'pr-'+agent,'quantity':qty,'product_name':sku,'sku':sku,
      'specifications':{'sku':sku,'material':'steel','color':'black'},
      'destination':{'province':'浙江','postal_code':'310000','city':'杭州'},'need_freight':False,
    }, buyer_aic)
    pay=payload_of(data)
    unit=pay.get('unit_price')
    print('SUP', agent, 'OK' if unit is not None else 'BAD', 'unit', unit)
    ok_sup = ok_sup and unit is not None

# 3) optional: discover suppliers via buyer tools if importable
try:
    import asyncio
    from commerce.discovery import discover_suppliers
    async def disc():
        return await discover_suppliers(query='脚轮', product_name='RM-CASTER-300', quantity=100, limit=5)
    d=asyncio.get_event_loop().run_until_complete(disc())
    cands=d.get('candidates') or []
    print('DISCOVER', d.get('source'), 'n', len(cands), [c.get('agent_id') or c.get('name') for c in cands[:5]])
except Exception as exc:
    print('DISCOVER_SKIP', type(exc).__name__, str(exc)[:160])

print('SUPPLIERS_OK' if ok_sup else 'SUPPLIERS_BAD')
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
    log_ok = ("LOGISTICS_OK" in out) or ("LOGISTICS_OK_SDK" in out)
    sup_ok = "SUPPLIERS_OK" in out
    print("LOGISTICS_COMM", "PASS" if log_ok else "FAIL", flush=True)
    print("SUPPLIER_COMM", "PASS" if sup_ok else "FAIL", flush=True)
    print("INTEROP_FINISH_PASS" if (log_ok and sup_ok) else "INTEROP_FINISH_PARTIAL", flush=True)
    return 0 if (log_ok and sup_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
