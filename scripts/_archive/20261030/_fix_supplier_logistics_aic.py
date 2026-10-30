# -*- coding: utf-8 -*-
"""Align LOGISTICS_AIC on Aliyun suppliers to Tencent logistics cert CN."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
HOST = "39.105.20.113"
CERT_CN = "1.2.156.3088.1.BUPT.2HY2P9.JOBNF9.39B1TM.0ALR"

REMOTE = rf"""
set -e
CN='{CERT_CN}'
for f in /opt/agentlink/.env /etc/agentlink/*.env; do
  [ -f "$f" ] || continue
  if grep -q '^LOGISTICS_AIC=' "$f"; then
    sed -i "s|^LOGISTICS_AIC=.*|LOGISTICS_AIC=$CN|" "$f"
    echo patched $f
  fi
done
grep LOGISTICS_AIC /opt/agentlink/.env || true
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 2
systemctl is-active agentlink-supplier-a
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(REMOTE, timeout=90)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    main()
