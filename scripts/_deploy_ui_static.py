# -*- coding: utf-8 -*-
"""Push ui/static (+ index) to both clouds and restart UI units."""
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

FILES = [
    "ui/static/app.js",
    "ui/static/index.html",
    "ui/static/styles.css",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        remote = f"/opt/agentlink/{rel}"
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> None:
    _, o, e = c.exec_command(cmd, timeout=120, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")


def main() -> None:
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(BUYER, username="root", pkey=paramiko.RSAKey.from_private_key_file(str(PEM)), timeout=40, allow_agent=False, look_for_keys=False)
    put(b, FILES)
    run(b, "systemctl restart agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics; sleep 2; systemctl is-active agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics")
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, FILES)
    run(s, "systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; sleep 2; systemctl is-active agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c")
    s.close()
    print("DEPLOY_UI_STATIC_DONE", flush=True)


if __name__ == "__main__":
    main()
