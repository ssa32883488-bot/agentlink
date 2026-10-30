# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

FILES = [
    "commerce/choice_actions.py",
    "commerce/buyer_tools/service.py",
    "commerce/chat_buyer_wit.py",
    "ui/static/app.js",
    "ui/static/styles.css",
    "ui/static/index.html",
    "docs/evidence/choice_actions_buttons.md",
    "scripts/_smoke_choice_actions.py",
]


def main() -> int:
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
    sftp = b.open_sftp()
    for rel in FILES:
        local = ROOT / rel
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = b.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(local), remote)
        print("put", rel, flush=True)
    sftp.close()
    _, o, e = b.exec_command(
        """
set -e
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-ui-buyer-a agentlink-ui-buyer-b
sleep 3
systemctl is-active agentlink-buyer-a agentlink-ui-buyer-a
cd /opt/agentlink && .venv/bin/python scripts/_smoke_choice_actions.py
""",
        timeout=120,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
