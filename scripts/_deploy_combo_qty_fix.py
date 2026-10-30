# -*- coding: utf-8 -*-
"""Deploy combo qty anti-sum fix to buyer cloud + run smoke."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"

FILES = [
    "agents/buyer_a/graph.py",
    "commerce/flow_service.py",
    "commerce/flow_routes.py",
    "commerce/chat_buyer_wit.py",
    "commerce/choice_actions.py",
    "commerce/buyer_tools/service.py",
    "scripts/_smoke_combo_qty_no_sum.py",
]


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = c.open_sftp()
    for rel in FILES:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()
    _, o, e = c.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 3; "
        "systemctl is-active agentlink-buyer-a agentlink-buyer-b; "
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python scripts/_smoke_combo_qty_no_sum.py",
        timeout=120,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    c.close()
    print("DEPLOY_COMBO_QTY_FIX_DONE", flush=True)


if __name__ == "__main__":
    main()
