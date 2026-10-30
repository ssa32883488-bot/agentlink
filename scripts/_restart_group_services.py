# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def run(host: str, auth: str, cmd: str) -> None:
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
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    c.close()


def main() -> None:
    print("=== restart tencent ===", flush=True)
    run(
        "81.70.46.119",
        "pem",
        """
set -e
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
sleep 5
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
curl -sk https://127.0.0.1:8010/health; echo
curl -sk https://127.0.0.1:8015/health; echo
cd /opt/agentlink
/opt/agentlink/.venv/bin/python -c 'from commerce import group_mq; print(group_mq.mq_rabbit_config())'
""",
    )
    print("=== restart aliyun ===", flush=True)
    run(
        "39.105.20.113",
        "pw",
        """
set -e
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 5
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for p in 8011 8013 8014; do echo PORT$p; curl -sk https://127.0.0.1:$p/health; echo; done
""",
    )


if __name__ == "__main__":
    main()
