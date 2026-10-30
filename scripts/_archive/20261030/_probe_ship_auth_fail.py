# -*- coding: utf-8 -*-
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
HOST = "81.70.46.119"
REMOTE = r"""
echo ===logistics last log===
tail -n 80 /var/log/agentlink/logistics.log | tail -n 60
echo ===buyer-a last log===
tail -n 40 /var/log/agentlink/buyer-a.log 2>/dev/null || tail -n 40 /var/log/agentlink/buyer_a.log 2>/dev/null || ls /var/log/agentlink/ | head
echo ===cert subjects===
openssl x509 -in /opt/agentlink/certs/platform/logistics/agent-cert.pem -noout -subject
openssl x509 -in /opt/agentlink/certs/platform/buyer-a/agent-cert.pem -noout -subject
echo ===aic envs===
grep LOGISTICS_AIC /etc/agentlink/buyer-a.env /etc/agentlink/logistics.env /opt/agentlink/.env
grep BUYER_A_AIC /etc/agentlink/logistics.env /opt/agentlink/.env | head
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST,
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
