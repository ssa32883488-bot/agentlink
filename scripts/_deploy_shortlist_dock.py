# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
FILES = ["ui/static/app.js", "ui/static/index.html", "ui/static/styles.css"]


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
        "systemctl restart agentlink-ui-buyer-a; sleep 2; systemctl is-active agentlink-ui-buyer-a; "
        "BUYER_AGENT_ID=buyer-a /opt/agentlink/.venv/bin/python -c "
        "\"from commerce import procurement_case as pc; "
        "cs=pc.list_cases(3); "
        "print([(x.get('case_id'), x.get('state'), len(x.get('candidates') or [])) for x in cs])\"",
        timeout=60,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    c.close()


if __name__ == "__main__":
    main()
