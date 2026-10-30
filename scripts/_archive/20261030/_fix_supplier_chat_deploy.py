# -*- coding: utf-8 -*-
"""Hotfix: deploy chat_sessions + supplier chat stack; restart both clouds."""
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

FILES_S = [
    "commerce/chat_sessions.py",
    "commerce/chat_supplier.py",
    "commerce/env_loader.py",
    "commerce/supplier_routes.py",
    "commerce/logistics_tickets.py",
    "commerce/order_tickets.py",
    "commerce/office_routes.py",
    "commerce/db.py",
    "commerce/notify.py",
    "commerce/tickets.py",
    "agents/supplier_common/freight.py",
    "ui/static/app.js",
    "ui/static/index.html",
    "ui/static/styles.css",
    "ui/config_supplier_a.yaml",
    "ui/config_supplier_b.yaml",
    "ui/config_supplier_c.yaml",
]
FILES_B = [
    "commerce/chat_sessions.py",
    "commerce/logistics_tickets.py",
    "commerce/order_tickets.py",
    "commerce/office_routes.py",
    "commerce/buyer_routes.py",
    "commerce/db.py",
    "ui/static/app.js",
    "ui/static/index.html",
    "ui/static/styles.css",
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


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", errors="replace")


def main() -> None:
    print("==== Aliyun suppliers ====", flush=True)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, FILES_S)
    run(
        s,
        """
set -e
cd /opt/agentlink
/opt/agentlink/.venv/bin/python -c "from commerce import chat_sessions, chat_supplier, logistics_tickets; print('import_ok')"
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c \\
  agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
sleep 6
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
curl -sk -m 10 https://127.0.0.1:8011/api/erp/chat-engine; echo
curl -sk -m 10 https://127.0.0.1:8011/api/erp/chat/threads; echo
""",
    )
    s.close()

    print("==== Tencent buyer/logistics ====", flush=True)
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
    put(b, FILES_B)
    run(
        b,
        """
set -e
systemctl restart agentlink-buyer-a agentlink-logistics agentlink-ui-buyer-a agentlink-ui-logistics
sleep 5
systemctl is-active agentlink-buyer-a agentlink-logistics
""",
    )
    b.close()
    print("FIX_DEPLOY_DONE", flush=True)


if __name__ == "__main__":
    main()
