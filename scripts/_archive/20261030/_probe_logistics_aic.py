# -*- coding: utf-8 -*-
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
REMOTE = r"""
grep -E 'LOGISTICS_AIC|LOGISTICS_RPC' /opt/agentlink/.env | head -20
echo ---
grep -n 'JOBNF9\|ZBD999' /opt/agentlink/.env /opt/agentlink/acs/*.json 2>/dev/null | head -30
echo ---
# logistics process env
tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value agentlink-logistics)/environ 2>/dev/null | grep -iE 'AIC|CERT' | head
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
    _, o, e = c.exec_command(REMOTE, timeout=40)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    main()
