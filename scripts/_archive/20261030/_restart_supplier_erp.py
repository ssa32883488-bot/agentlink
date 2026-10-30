# -*- coding: utf-8 -*-
"""Restart Aliyun supplier Java + Python ERP sidecars after negotiate.py change."""
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem")

REMOTE = r"""
set -e
echo '=== ports ==='
ss -lntp | grep -E '1801|801' || true
echo '=== units ==='
systemctl list-units --type=service --all 'agentlink*' --no-pager | head -40
echo '=== find erp ==='
ps aux | grep -E 'erp|supplier|1801' | grep -v grep | head -30
# common patterns
for u in agentlink-erp-supplier-a agentlink-supplier-a-erp agentlink-supplier-erp \
         agentlink-py-supplier-a agentlink-supplier-a-py; do
  systemctl cat "$u" 2>/dev/null | head -5 && echo UNIT=$u
done
ls /etc/systemd/system/agentlink* 2>/dev/null
ls /opt/agentlink/java-suppliers 2>/dev/null | head
# put latest negotiate into place already done; restart anything python-related for suppliers
for u in $(systemctl list-units --type=service --all --no-legend 'agentlink*' | awk '{print $1}'); do
  if systemctl cat "$u" 2>/dev/null | grep -qiE 'python|18011|18012|18013|erp|negotiate|graph'; then
    echo RESTART $u
    systemctl restart "$u" || true
  fi
done
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c || true
sleep 3
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
ss -lntp | grep -E '1801|8011|8012|8013' || true
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
    _, o, e = c.exec_command(REMOTE, timeout=120, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()

    # also push buyer service.py sku fix to tencent
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    c2 = paramiko.SSHClient()
    c2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c2.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(PEM),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = c2.open_sftp()
    sftp.put(str(root / "commerce/buyer_tools/service.py"), "/opt/agentlink/commerce/buyer_tools/service.py")
    sftp.put(str(root / "agents/supplier_common/negotiate.py"), "/opt/agentlink/agents/supplier_common/negotiate.py")
    print("put tencent buyer+negotiate", flush=True)
    sftp.close()
    _, o, e = c2.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 3; systemctl is-active agentlink-buyer-a",
        timeout=60,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c2.close()


if __name__ == "__main__":
    main()
