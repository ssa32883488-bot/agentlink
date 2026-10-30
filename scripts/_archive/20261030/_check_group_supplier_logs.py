# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def dump(host: str, auth: str, cmd: str) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = dict(
        hostname=host,
        username="root",
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    if auth == "pem":
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    _, o, e = c.exec_command(cmd, timeout=60, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    c.close()


def main() -> None:
    print("=== aliyun supplier logs ===", flush=True)
    dump(
        "39.105.20.113",
        "pw",
        r"""
for u in agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; do
  echo ===== $u =====
  journalctl -u $u -n 80 --no-pager 2>/dev/null | grep -iE 'group|join|ping|task_command|identity|error|amqp|rabbit' || true
done
# env binding
grep -E 'AIP_IDENTITY|ACPS_MQ|AIP_CLIENT' /opt/agentlink/.env | head -30
""",
    )
    print("=== tencent logistics/buyer logs ===", flush=True)
    dump(
        "81.70.46.119",
        "pem",
        r"""
for u in agentlink-logistics agentlink-buyer-a; do
  echo ===== $u =====
  journalctl -u $u -n 80 --no-pager 2>/dev/null | grep -iE 'group|join|ping|invite|task_command|identity|error|amqp' || true
done
grep -E 'AIP_IDENTITY|ACPS_MQ|AIP_CLIENT' /opt/agentlink/.env | head -30
""",
    )


if __name__ == "__main__":
    main()
