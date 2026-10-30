# -*- coding: utf-8 -*-
from __future__ import annotations

import os

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
    _, o, e = c.exec_command(
        r"""
set +e
systemctl is-active agentlink-supplier-c
grep SUPPLIER_C_AIC /opt/agentlink/.env /etc/agentlink/supplier-c.env 2>/dev/null
for i in 1 2 3 4 5 6; do
  curl -sk --connect-timeout 3 https://127.0.0.1:8014/health; echo
  code=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8014/health || true)
  [ "$code" = 200 ] && break
  sleep 5
done
tail -n 25 /var/log/agentlink/supplier-c.log 2>/dev/null | tail -n 25
""",
        timeout=90,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
