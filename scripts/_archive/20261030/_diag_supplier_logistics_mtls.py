"""Diagnose supplier→logistics AIP auth."""
from __future__ import annotations

import os

import paramiko

SUPPLIER_PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem")


def run(host: str, *, password: str | None = None, cmd: str) -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        c.connect(host, username="root", password=password, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            host,
            username="root",
            pkey=paramiko.RSAKey.from_private_key_file(PEM),
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    _, o, _ = c.exec_command(cmd, timeout=60, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    c.close()
    return out


print("==== supplier env/certs ====")
print(
    run(
        "39.105.20.113",
        password=SUPPLIER_PW,
        cmd=r"""
cd /opt/agentlink
grep -E '^(AIP_|LOGISTICS_)' .env | sed 's/=.*/=***/' 
ls -la certs/platform/supplier-a 2>/dev/null | head
ls -la certs/platform/*.pem 2>/dev/null | head
# show actual AIP client paths if set
grep -E '^(AIP_CLIENT_|AIP_TRUST|AIP_IDENTITY)' .env || true
""",
    )
)

print("==== logistics env on tencent ====")
print(
    run(
        "81.70.46.119",
        cmd=r"""
cd /opt/agentlink
grep -E '^(AIP_|AIP_IDENTITY)' .env || true
systemctl cat agentlink-logistics | head -40
journalctl -u agentlink-logistics -n 15 --no-pager | tail -n 15
""",
    )
)
