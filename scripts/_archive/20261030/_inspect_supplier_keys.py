# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

CMD = r"""
echo '=== key file sizes ==='
ls -la /opt/agentlink/certs/platform/supplier-a/ /etc/agentlink/tls/aic/supplier-a/
echo '=== key head ==='
head -c 200 /opt/agentlink/certs/platform/supplier-a/server-key.pem; echo
file /opt/agentlink/certs/platform/supplier-a/server-key.pem /etc/agentlink/tls/aic/supplier-a/server.key
echo '=== java log tail ==='
tail -40 /var/log/agentlink/supplier-a.log
echo '=== process / listen ==='
systemctl is-active agentlink-supplier-a
ss -lntp | grep 8011 || true
echo '=== find real keys ==='
find /opt/agentlink/certs /etc/agentlink/tls -type f \( -name '*.pem' -o -name '*.key' -o -name '*.crt' \) -exec ls -la {} \; 2>/dev/null | head -80
"""


def main() -> None:
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = s.exec_command(CMD, timeout=60)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    s.close()


if __name__ == "__main__":
    main()
