# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    cmd = r"""
set -e
echo '--- certs ---'
ls -la /opt/agentlink/certs/platform/supplier-a/ 2>/dev/null | head
grep -E 'AIP_CLIENT|AIP_TRUST|AIP_IDENTITY' /opt/agentlink/.env | head -20
echo '--- journal supplier-a last 40 ---'
journalctl -u agentlink-supplier-a -n 40 --no-pager
echo '--- uvicorn/app log files ---'
ls -lt /tmp/*.log /var/log/agentlink/* 2>/dev/null | head -20
tail -n 50 /var/log/agentlink/supplier-a.log 2>/dev/null || true
"""
    _, o, e = c.exec_command(cmd, timeout=60, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    c.close()


if __name__ == "__main__":
    main()
