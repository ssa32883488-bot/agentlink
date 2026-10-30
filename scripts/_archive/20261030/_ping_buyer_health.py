# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE = r"""
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
curl -sk -o /tmp/tix.json -w 'tickets=%{http_code}\n' https://127.0.0.1:8010/api/erp/tickets
python3 - <<'PY'
import json
d=json.load(open('/tmp/tix.json'))
print('n', len(d.get('items') or []))
PY
"""


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
    _, o, e = c.exec_command(REMOTE, timeout=30)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    main()
