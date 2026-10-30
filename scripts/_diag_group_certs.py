# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _i, o, e = c.exec_command(cmd, timeout=60)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def main() -> None:
    for role in ("buyer", "supplier"):
        print(f"\n======== {role} ========")
        c = connect(role)
        print(
            run(
                c,
                "ls -la /opt/agentlink/certs/platform 2>/dev/null | head -40; "
                "echo '--- dirs ---'; ls /opt/agentlink/certs/platform 2>/dev/null; "
                "for d in buyer-a buyer-b logistics supplier-a supplier-b supplier-c; do "
                "  echo \"## $d\"; ls -la /opt/agentlink/certs/platform/$d 2>/dev/null | head -10; "
                "done; "
                "echo '--- env cert ---'; "
                "grep -E 'AIP_CLIENT|TRUST_BUNDLE|ACPS_MQ|GROUP|V2_TRY' /opt/agentlink/.env 2>/dev/null | sed 's/PASSWORD=.*/PASSWORD=***/'; "
                "echo '--- systemd buyer-a ---'; "
                "systemctl show agentlink-buyer-a -p Environment --no-pager 2>/dev/null | tr ' ' '\\n' | grep -E 'AIP_|ACPS_|V2_' | head -40; "
                "echo '--- find certs ---'; "
                "find /opt/agentlink/certs /etc/agentlink -name 'agent-cert.pem' 2>/dev/null | head -30; "
                "find /opt/agentlink /etc/agentlink -name 'trust-bundle.pem' 2>/dev/null | head -20",
            )
        )
        c.close()


if __name__ == "__main__":
    main()
