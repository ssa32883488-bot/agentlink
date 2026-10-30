# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
FILES = ["commerce/buyer_tools/service.py", "ui/static/app.js"]


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
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
        "systemctl restart agentlink-buyer-a agentlink-buyer-b "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b 2>/dev/null; "
        "sleep 3; systemctl is-active agentlink-buyer-a",
        timeout=90,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
