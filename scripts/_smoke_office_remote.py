# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce/mailbox.py",
    "commerce/tickets.py",
    "commerce/office_routes.py",
    "commerce/db.py",
    "commerce/buyer_routes.py",
    "commerce/supplier_routes.py",
    "commerce/merchant_profiles.yaml",
    "agents/logistics/main.py",
    "ui/static/app.js",
    "ui/static/index.html",
    "ui/static/styles.css",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()


def main() -> None:
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
    put(b, FILES)
    remote = r"""
set -e
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics \
  agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics
sleep 3
/opt/agentlink/.venv/bin/python <<'PY'
import json, urllib.request, ssl
ctx = ssl._create_unverified_context()

def call(port, path, data=None):
    url = f"https://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method="GET" if data is None else "POST")
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, context=ctx, timeout=45) as r:
        return json.loads(r.read().decode())

print("mail", call(8010, "/api/erp/mailbox").get("email"))
t = call(8010, "/api/erp/tickets", {
    "title": "云上冒烟工单",
    "kind": "procurement",
    "peer_agent_id": "supplier-a",
    "state": {"step": "rfq"},
})
print("ticket", t["id"], t["status"])
s = call(8010, f"/api/erp/tickets/{t['id']}/suspend", {"reason": "pause", "state": {"step": "suspended"}})
print("suspend", s["status"])
r = call(8010, f"/api/erp/tickets/{t['id']}/resume", {})
print("resume", r["status"], r.get("state"))
docs = call(8010, f"/api/erp/tickets/{t['id']}/send-final-docs", {
    "to_agent": "supplier-a",
    "order_doc": {"order_no": "EO-SMOKE", "summary": "冒烟电子订单"},
    "invoice_doc": {"invoice_no": "EI-SMOKE", "summary": "冒烟电子发票"},
})
print("order_delivery", (docs.get("order_mail") or {}).get("delivery"))
print("inv_delivery", (docs.get("invoice_mail") or {}).get("delivery"))
tf = call(8010, f"/api/erp/tickets/{t['id']}")
print("completion", tf.get("completion"), "status", tf.get("status"))
print("events", len(tf.get("events") or []))
PY
"""
    _, o, e = b.exec_command(remote, timeout=180, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, [
        "commerce/mailbox.py",
        "commerce/tickets.py",
        "commerce/office_routes.py",
        "commerce/db.py",
        "commerce/supplier_routes.py",
        "commerce/merchant_profiles.yaml",
        "ui/static/app.js",
        "ui/static/index.html",
        "ui/static/styles.css",
    ])
    _, o, e = s.exec_command(
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c "
        "agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; sleep 3; "
        "curl -sk https://127.0.0.1:8011/api/erp/mailbox | head -c 300; echo; "
        "curl -sk 'https://127.0.0.1:8011/api/erp/tickets?include_archived=true' | head -c 400; echo",
        timeout=120,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    s.close()
    print("SMOKE_OFFICE_DONE", flush=True)


if __name__ == "__main__":
    main()
