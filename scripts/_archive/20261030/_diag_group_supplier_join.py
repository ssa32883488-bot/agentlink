# -*- coding: utf-8 -*-
"""在阿里云 supplier-a 上复现 join 后是否仍在消费，并打日志。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE = r"""
set -e
cd /opt/agentlink
tail -n 80 /var/log/agentlink/supplier-a.log
echo '===== after join markers ====='
grep -nE 'group/join|partner_join|task_command|queue_created|Consumer|Error|Traceback|ping' /var/log/agentlink/supplier-a.log | tail -40
echo '===== systemd status ====='
systemctl status agentlink-supplier-a --no-pager | head -20
"""


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
    _, o, e = c.exec_command(REMOTE, timeout=60, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    c.close()


if __name__ == "__main__":
    main()
