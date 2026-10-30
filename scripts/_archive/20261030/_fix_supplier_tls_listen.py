# -*- coding: utf-8 -*-
"""Diagnose supplier-a TLS listen + which cert uvicorn loads."""
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

CMD = r"""
set -x
systemctl status agentlink-supplier-a --no-pager -l | head -40
echo '==== unit ===='
cat /etc/systemd/system/agentlink-supplier-a.service
echo '==== env cert paths ===='
grep -E 'AIP_SERVER|AIP_CLIENT|PORT|SSL' /etc/agentlink/supplier-a.env
echo '==== cert mtime/CN ===='
ls -la /opt/agentlink/certs/platform/supplier-a/
openssl x509 -in /opt/agentlink/certs/platform/supplier-a/server-cert.pem -noout -subject -dates
echo '==== journal ===='
journalctl -u agentlink-supplier-a -n 40 --no-pager
echo '==== all listeners ===='
ss -lntp | head -60
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
