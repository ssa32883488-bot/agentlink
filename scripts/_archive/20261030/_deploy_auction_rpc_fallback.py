# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


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
    sftp.put(str(ROOT / "commerce/flow_service.py"), "/opt/agentlink/commerce/flow_service.py")
    sftp.close()
    print("put flow_service.py", flush=True)
    _, o, e = c.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 4; "
        "systemctl is-active agentlink-buyer-a",
        timeout=60,
    )
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()
    print("DEPLOY_AUCTION_FALLBACK_DONE", flush=True)


if __name__ == "__main__":
    main()
