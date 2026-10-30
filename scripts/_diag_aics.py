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
        print("====", role)
        c = connect(role)
        print(
            run(
                c,
                "grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_|.*_AIC=)' /opt/agentlink/.env 2>/dev/null | head -40; "
                "echo '--- summary ---'; python3 -c 'import json;print(json.load(open(\"/opt/agentlink/certs/platform/summary.json\")))' 2>/dev/null | head -c 2000; echo; "
                "echo '--- eab buyer-a ---'; cat /opt/agentlink/certs/platform/buyer-a/eab.json; echo; "
                "echo '--- openssl CN ---'; "
                "for d in buyer-a buyer-b logistics supplier-a supplier-b supplier-c; do "
                "  echo -n \"$d: \"; openssl x509 -in /opt/agentlink/certs/platform/$d/agent-cert.pem -noout -subject 2>/dev/null; "
                "done; "
                "echo '--- systemd EnvironmentFile ---'; "
                "systemctl cat agentlink-buyer-a --no-pager 2>/dev/null | head -35; "
                "ls /opt/agentlink/agents/buyer_a/*.env 2>/dev/null; "
                "grep -RIn 'BUYER_A_AIC\\|1\\.2\\.156' /opt/agentlink/.env /opt/agentlink/agents/buyer_a /etc/systemd/system/agentlink-buyer-a.service 2>/dev/null | head -30",
            )
        )
        c.close()


if __name__ == "__main__":
    main()
