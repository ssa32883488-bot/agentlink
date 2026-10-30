# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(
        r"""
set +e
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
ss -lntp | grep -E '8011|8013|8014' || netstat -lntp | grep -E '8011|8013|8014' || true
echo '=== tail a ==='
tail -n 40 /var/log/agentlink/supplier-a.log 2>/dev/null || journalctl -u agentlink-supplier-a -n 40 --no-pager
echo '=== unit SSL ==='
grep SSL_ /etc/systemd/system/agentlink-supplier-a.service
ls -la /etc/agentlink/tls/aic/supplier-a/
""",
        timeout=40,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
