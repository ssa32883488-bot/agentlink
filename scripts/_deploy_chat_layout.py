# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
FILES = ["ui/static/styles.css", "ui/static/app.js", "ui/static/index.html"]


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
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()
    _, o, e = b.exec_command(
        "systemctl restart agentlink-ui-buyer-a agentlink-ui-buyer-b; sleep 2; "
        "systemctl is-active agentlink-ui-buyer-a; "
        "grep -n '7.5rem\\|chatlayout3\\|choice-head' /opt/agentlink/ui/static/styles.css /opt/agentlink/ui/static/index.html | head -20",
        timeout=60,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
