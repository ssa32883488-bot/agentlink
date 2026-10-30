# -*- coding: utf-8 -*-
"""Deploy mailbox/tickets/office UI to both clouds."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "commerce/db.py",
    "commerce/mailbox.py",
    "commerce/tickets.py",
    "commerce/notify.py",
    "commerce/order_tickets.py",
    "commerce/order_provenance.py",
    "commerce/logistics_tickets.py",
    "commerce/office_routes.py",
    "commerce/flow_service.py",
    "commerce/buyer_routes.py",
    "commerce/supplier_routes.py",
    "commerce/chat_sessions.py",
    "commerce/chat_supplier.py",
    "commerce/merchant_profiles.yaml",
    "agents/logistics/main.py",
    "agents/supplier_common/freight.py",
    "ui/static/app.js",
    "ui/static/index.html",
    "ui/static/styles.css",
    "ui/config_buyer_a.yaml",
    "docs/office_mailbox_tickets.md",
]

SUPPLIER_FILES = [
    "commerce/db.py",
    "commerce/mailbox.py",
    "commerce/tickets.py",
    "commerce/notify.py",
    "commerce/order_tickets.py",
    "commerce/order_provenance.py",
    "commerce/logistics_tickets.py",
    "commerce/office_routes.py",
    "commerce/supplier_routes.py",
    "commerce/chat_sessions.py",
    "commerce/chat_supplier.py",
    "commerce/env_loader.py",
    "commerce/merchant_profiles.yaml",
    "agents/supplier_common/freight.py",
    "ui/static/app.js",
    "ui/static/index.html",
    "ui/static/styles.css",
    "ui/config_supplier_a.yaml",
    "ui/config_supplier_b.yaml",
    "ui/config_supplier_c.yaml",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = c.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> None:
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")


def main() -> None:
    print("==== Tencent ====", flush=True)
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
    put(b, BUYER_FILES)
    run(
        b,
        r"""
set -e
cd /opt/agentlink
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics \
  agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics
sleep 4
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
# smoke: order ticket spawn → bilateral ack → docs
/opt/agentlink/.venv/bin/python - <<'PY'
import json, urllib.request, ssl, sys
sys.path.insert(0, '/opt/agentlink')
ctx=ssl._create_unverified_context()
def call(port, path, data=None):
    req=urllib.request.Request(f'https://127.0.0.1:{port}{path}', method='GET' if data is None else 'POST')
    if data is not None:
        body=json.dumps(data).encode()
        req.data=body
        req.add_header('Content-Type','application/json')
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return json.loads(r.read().decode())
from commerce.order_tickets import spawn_order_ticket_from_case, ack_order_generated
case={
  'case_id':'case-smoke-ord',
  'selected_supplier':'supplier-a',
  'brief':{'product_name':'冒烟座椅','quantity':10},
  'order_draft':{'payload':{'unit_price':39.39,'goods_total':393.9,'freight_amount':20,'currency':'CNY','product_name':'冒烟座椅','quantity':10}},
}
meta=spawn_order_ticket_from_case(case, buyer_agent_id='buyer-a')
print('spawn', meta)
tid=meta.get('ticket_id')
assert tid, meta
ntf=call(8010,'/api/erp/notifications?unread_only=true')
print('buyer_ntf', len(ntf.get('items') or []), [n.get('title') for n in (ntf.get('items') or [])[:3]])
t1=ack_order_generated('buyer-a', tid, sync_peer=True)
print('buyer_ack', (t1.get('state') or t1.get('ticket',{}).get('state') or {}).get('order_status') if isinstance(t1, dict) else t1)
print('ok')
PY
""",
    )
    b.close()

    print("==== Aliyun ====", flush=True)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, SUPPLIER_FILES)
    run(
        s,
        r"""
set -e
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c \
  agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
sleep 4
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
/opt/agentlink/.venv/bin/python - <<'PY'
import json, urllib.request, ssl
ctx=ssl._create_unverified_context()
def call(port, path, data=None):
    req=urllib.request.Request(f'https://127.0.0.1:{port}{path}', method='GET' if data is None else 'POST')
    if data is not None:
        body=json.dumps(data).encode()
        req.data=body
        req.add_header('Content-Type','application/json')
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return json.loads(r.read().decode())
items=call(8011,'/api/erp/tickets').get('items') or []
ord_t=[t for t in items if t.get('kind')=='order' and str(t.get('id','')).startswith('tk-ord-')]
print('supplier_order_tickets', len(ord_t), [t.get('id') for t in ord_t[:3]])
ntf=call(8011,'/api/erp/notifications?unread_only=true')
print('supplier_ntf', len(ntf.get('items') or []), [n.get('title') for n in (ntf.get('items') or [])[:3]])
if ord_t:
    tid=ord_t[0]['id']
    st=ord_t[0].get('state') or {}
    if not st.get('supplier_order_ack'):
        r=call(8011, f'/api/erp/tickets/{tid}/ack-order', {})
        print('supplier_ack', (r.get('state') or (r.get('ticket') or {}).get('state') or {}).get('order_status'))
    print('supplier_mail', len((call(8011,'/api/erp/mailbox').get('items') or [])))
print('ok')
PY
""",
    )
    s.close()
    print("DEPLOY_OFFICE_DONE", flush=True)


if __name__ == "__main__":
    main()
