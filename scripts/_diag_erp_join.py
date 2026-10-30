# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    cmd = r"""
set -e
echo '=== erp health ==='
curl -s --max-time 5 http://127.0.0.1:18011/health; echo
echo '=== erp join empty ==='
curl -s --max-time 5 -X POST http://127.0.0.1:18011/group/join -H 'Content-Type: application/json' -d '{}' | head -c 300; echo
echo '=== java join empty ==='
curl -sk --max-time 5 -X POST https://127.0.0.1:8011/group/join -H 'Content-Type: application/json' -d '{}' | head -c 300; echo
echo '=== java routes? ==='
journalctl -u agentlink-supplier-a -n 30 --no-pager | grep -iE 'group|join|500|Error|Exception' | tail -20
echo '=== erp unit ==='
systemctl cat agentlink-supplier-a-erp | head -40
echo '=== nginx/proxy ==='
grep -R 'group/join\|18011\|proxy_pass' /etc/nginx /opt/agentlink -n 2>/dev/null | head -30
ls /opt/agentlink/java* 2>/dev/null | head
"""
    _, o, e = c.exec_command(cmd, timeout=60, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace")[-8000:])
    c.close()


if __name__ == "__main__":
    main()
