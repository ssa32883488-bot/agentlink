# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

CMD = r"""
cd /opt/agentlink
echo '=== jar group classes ==='
jar tf supplier-a.jar 2>/dev/null | grep -i group | head -40
echo '=== erp recent join ==='
tail -n 200 /var/log/agentlink/supplier-a-erp.log | grep -iE 'group|join|Error|Traceback|Validation|Exception' | tail -50
echo '=== java recent ==='
tail -n 200 /var/log/agentlink/supplier-a.log | grep -iE 'group|join|Error|Exception|500' | tail -40
echo '=== sample invite via buyer curl shape ==='
# pull last invite body shape from buyer if any
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(CMD, timeout=60, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace")[-8000:])
    c.close()


if __name__ == "__main__":
    main()
