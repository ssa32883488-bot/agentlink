# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce/order_tickets.py",
    "commerce/choice_actions.py",
    "commerce/chat_buyer_wit.py",
    "commerce/buyer_tools/service.py",
    "commerce/flow_service.py",
    "commerce/logistics_tickets.py",
]


def put(host: str, *, pem: bool, restart: str) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    sftp = c.open_sftp()
    for rel in FILES:
        local = ROOT / rel
        if local.is_file():
            sftp.put(str(local), f"/opt/agentlink/{rel}")
            print("put", host, rel, flush=True)
    sftp.close()
    _, o, e = c.exec_command(restart, timeout=90, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()


def main() -> None:
    put(
        "81.70.46.119",
        pem=True,
        restart=(
            "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
            "sleep 4; systemctl is-active agentlink-buyer-a"
        ),
    )
    put(
        "39.105.20.113",
        pem=False,
        restart=(
            "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
            "sleep 2; echo aliyun_ok"
        ),
    )
    print("DEPLOY_DIALOG_FLOW_DONE", flush=True)


if __name__ == "__main__":
    main()
