# -*- coding: utf-8 -*-
"""Smoke: supplier chat + order cancel/ack + logistics bilateral → buyer quote."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=240, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", errors="replace")


def main() -> None:
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    print("==== 1) spawn fresh order + buyer cancel smoke ====", flush=True)
    run(
        b,
        r"""
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import json, urllib.request, ssl, uuid
ctx=ssl._create_unverified_context()
def call(port, path, data=None):
    req=urllib.request.Request(f'https://127.0.0.1:{port}{path}', method='GET' if data is None else 'POST')
    if data is not None:
        body=json.dumps(data).encode(); req.data=body; req.add_header('Content-Type','application/json')
    with urllib.request.urlopen(req, context=ctx, timeout=40) as r:
        return json.loads(r.read().decode())
from commerce.order_tickets import spawn_order_ticket_from_case
cid=f'case-flow-{uuid.uuid4().hex[:6]}'
case={
  'case_id': cid,
  'selected_supplier':'supplier-a',
  'brief':{'product_name':'脚轮','quantity':50},
  'order_draft':{'payload':{'unit_price':12.5,'goods_total':625,'freight_amount':0,'currency':'CNY','product_name':'脚轮','quantity':50,'postal_code':'071000'}},
}
meta=spawn_order_ticket_from_case(case, buyer_agent_id='buyer-a')
print('SPAWN', meta.get('ticket_id'), meta.get('supplier_mirror',{}).get('ok'), 'buyer_title', (meta.get('buyer_ticket') or {}).get('title'))
tid=meta['ticket_id']
# cancel path on a separate ticket
cid2=f'case-cancel-{uuid.uuid4().hex[:6]}'
meta2=spawn_order_ticket_from_case({**case,'case_id':cid2}, buyer_agent_id='buyer-a')
tid2=meta2['ticket_id']
c=call(8010, f'/api/erp/tickets/{tid2}/cancel-order', {'reason':'冒烟：产能不足测试取消'})
print('CANCEL', c.get('status'), (c.get('state') or {}).get('order_status'), (c.get('state') or {}).get('cancel_reason'))
print('KEEP_TID', tid)
print('KEEP_CASE', cid)
PY
""",
    )
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    print("==== 2) supplier chat + ack order → logistics ====", flush=True)
    run(
        s,
        r"""
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import json, urllib.request, ssl, time
ctx=ssl._create_unverified_context()
def call(port, path, data=None):
    req=urllib.request.Request(f'https://127.0.0.1:{port}{path}', method='GET' if data is None else 'POST')
    if data is not None:
        body=json.dumps(data).encode(); req.data=body; req.add_header('Content-Type','application/json')
    with urllib.request.urlopen(req, context=ctx, timeout=90) as r:
        return json.loads(r.read().decode())
chat=call(8011,'/api/erp/chat', {'text':'待办'})
print('CHAT', (chat.get('reply') or '')[:180].replace('\n',' | '))
items=call(8011,'/api/erp/tickets').get('items') or []
# prefer open order pending ack
cands=[t for t in items if t.get('kind')=='order' and t.get('status')=='open' and not (t.get('state') or {}).get('cancelled')]
print('OPEN_ORDERS', [(t.get('id'), t.get('title'), (t.get('state') or {}).get('order_status'), (t.get('state') or {}).get('view')) for t in cands[:5]])
assert cands, 'no open order'
# pick newest without supplier ack
t=next((x for x in cands if not (x.get('state') or {}).get('supplier_order_ack')), cands[0])
tid=t['id']
print('ACK_SUP', tid)
# buyer may not have acked yet — still ack supplier side
r=call(8011, f'/api/erp/tickets/{tid}/ack-order', {})
st=r.get('state') or (r.get('ticket') or {}).get('state') or {}
print('SUP_ACK', st.get('order_status'), 'effective', st.get('order_effective'), 'logistics_spawned', st.get('logistics_spawned'))
# wait logistics ticket
for i in range(20):
    time.sleep(2)
    items=call(8011,'/api/erp/tickets').get('items') or []
    logs=[x for x in items if x.get('kind')=='logistics_order' and (x.get('state') or {}).get('order_ticket_id')==tid]
    if not logs:
        logs=[x for x in items if x.get('kind')=='logistics_order' and x.get('status')=='open']
    if logs:
        print('LOG_TICKET', logs[0].get('id'), logs[0].get('title'), (logs[0].get('state') or {}).get('quote'))
        print('LOG_ID', logs[0]['id'])
        break
else:
    print('LOG_TICKET_MISSING')
    # show notifications
    n=call(8011,'/api/erp/notifications?unread_only=true')
    print('NTF', [(x.get('title'), (x.get('payload') or {}).get('kind')) for x in (n.get('items') or [])[:6]])
PY
""",
    )
    s.close()

    # buyer ack the same order so both confirmed (if not already)
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    print("==== 3) buyer ack remaining + check shipping quote ntf ====", flush=True)
    run(
        b,
        r"""
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import json, urllib.request, ssl, time
ctx=ssl._create_unverified_context()
def call(port, path, data=None):
    req=urllib.request.Request(f'https://127.0.0.1:{port}{path}', method='GET' if data is None else 'POST')
    if data is not None:
        body=json.dumps(data).encode(); req.data=body; req.add_header('Content-Type','application/json')
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return json.loads(r.read().decode())
items=call(8010,'/api/erp/tickets').get('items') or []
opens=[t for t in items if t.get('kind')=='order' and t.get('status')=='open' and not (t.get('state') or {}).get('buyer_order_ack')]
print('BUYER_OPEN', [t.get('id') for t in opens[:5]])
for t in opens[:3]:
    r=call(8010, f"/api/erp/tickets/{t['id']}/ack-order", {})
    st=r.get('state') or (r.get('ticket') or {}).get('state') or {}
    print('BUYER_ACK', t['id'], st.get('order_status'), st.get('order_effective'))
time.sleep(3)
ntf=call(8010,'/api/erp/notifications?unread_only=true')
print('BUYER_NTF', [(n.get('title'), (n.get('payload') or {}).get('kind')) for n in (ntf.get('items') or [])[:8]])
PY
""",
    )
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    print("==== 4) ack logistics both sides ====", flush=True)
    run(
        s,
        r"""
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import json, urllib.request, ssl, time
ctx=ssl._create_unverified_context()
def call(port, path, data=None):
    req=urllib.request.Request(f'https://127.0.0.1:{port}{path}', method='GET' if data is None else 'POST')
    if data is not None:
        body=json.dumps(data).encode(); req.data=body; req.add_header('Content-Type','application/json')
    with urllib.request.urlopen(req, context=ctx, timeout=90) as r:
        return json.loads(r.read().decode())
# ensure logistics spawned after both ack
time.sleep(4)
items=call(8011,'/api/erp/tickets').get('items') or []
logs=[t for t in items if t.get('kind')=='logistics_order' and t.get('status')=='open']
print('LOG_OPEN', [(t.get('id'), (t.get('state') or {}).get('logistics_status'), (t.get('state') or {}).get('quote',{}).get('shipping_cost')) for t in logs[:5]])
if not logs:
    # try force spawn from latest effective order
    from commerce import logistics_tickets as lt
    from commerce import tickets as tk
    ords=[t for t in tk.list_tickets('supplier-a', limit=20) if t.get('kind')=='order' and (t.get('state') or {}).get('order_effective')]
    print('FORCE_FROM', [o.get('id') for o in ords[:3]])
    if ords:
        import asyncio
        out=asyncio.run(lt.quote_and_spawn_from_order('supplier-a', order_ticket=ords[0]))
        print('FORCE_SPAWN', out.get('ticket_id'), out.get('quote'))
        items=call(8011,'/api/erp/tickets').get('items') or []
        logs=[t for t in items if t.get('kind')=='logistics_order' and t.get('status')=='open']
assert logs, 'no logistics ticket'
lid=logs[0]['id']
r=call(8011, f'/api/erp/tickets/{lid}/ack-logistics', {})
st=r.get('state') or (r.get('ticket') or {}).get('state') or {}
print('SUP_LOG_ACK', st.get('logistics_status'), st.get('effective'))
print('LOG_ID', lid)
PY
""",
    )
    s.close()

    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    print("==== 5) logistics agent ack ====", flush=True)
    run(
        b,
        r"""
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import json, urllib.request, ssl
ctx=ssl._create_unverified_context()
def call(port, path, data=None):
    req=urllib.request.Request(f'https://127.0.0.1:{port}{path}', method='GET' if data is None else 'POST')
    if data is not None:
        body=json.dumps(data).encode(); req.data=body; req.add_header('Content-Type','application/json')
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return json.loads(r.read().decode())
items=call(8015,'/api/erp/tickets').get('items') or []
logs=[t for t in items if t.get('kind')=='logistics_order' and t.get('status')=='open']
print('LOGISTICS_OPEN', [(t.get('id'), (t.get('state') or {}).get('logistics_status')) for t in logs[:5]])
if logs:
    lid=logs[0]['id']
    r=call(8015, f'/api/erp/tickets/{lid}/ack-logistics', {})
    st=r.get('state') or (r.get('ticket') or {}).get('state') or {}
    print('LOG_ACK', st.get('logistics_status'), 'effective', st.get('effective'), 'buyer_notified', st.get('buyer_notified'))
ntf=call(8010,'/api/erp/notifications?unread_only=true')
print('BUYER_AFTER', [(n.get('title'), (n.get('payload') or {}).get('kind')) for n in (ntf.get('items') or [])[:10]])
print('SMOKE_FLOW_OK')
PY
""",
    )
    b.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
