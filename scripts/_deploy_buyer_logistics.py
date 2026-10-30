# -*- coding: utf-8 -*-
"""Deploy: logistics orders initiated by buyer, not supplier."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce/order_tickets.py",
    "commerce/logistics_tickets.py",
    "agents/supplier_common/freight.py",
    "ui/static/app.js",
]


def put_all(host: str, *, pem: bool) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = {
        "hostname": host,
        "username": "root",
        "timeout": 40,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    sftp = c.open_sftp()
    for rel in FILES:
        local = ROOT / rel
        if not local.is_file():
            print("skip missing", rel, flush=True)
            continue
        remote = f"/opt/agentlink/{rel}"
        sftp.put(str(local), remote)
        print("put", host, rel, flush=True)
    sftp.close()
    if pem:
        cmd = (
            "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
            "sleep 3; systemctl is-active agentlink-buyer-a agentlink-logistics"
        )
    else:
        cmd = (
            "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c "
            "2>/dev/null; sleep 2; echo aliyun_ok"
        )
    _, o, e = c.exec_command(cmd, timeout=90, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()


def main() -> None:
    print("==== tencent ====", flush=True)
    put_all("81.70.46.119", pem=True)
    print("==== aliyun ====", flush=True)
    put_all("39.105.20.113", pem=False)
    print("DEPLOY_BUYER_LOGISTICS_DONE", flush=True)


if __name__ == "__main__":
    main()
