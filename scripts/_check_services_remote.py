# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def run(host: str, *, pem: bool, cmd: str) -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if pem:
        c.connect(
            host,
            username="root",
            pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    else:
        c.connect(host, username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    _i, o, _e = c.exec_command(cmd, timeout=90, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    c.close()
    return out


BUYER_CMD = r"""
echo '=== units ==='
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics 2>/dev/null
systemctl list-units --type=service --all 'agentlink*' --no-pager 2>/dev/null | head -40
echo '=== listen ==='
ss -lntp | grep -E ':8010|:8012|:8015|:8090|:8092|:8095' || true
echo '=== local curl ==='
for u in \
  https://127.0.0.1:8090/api/domain \
  https://127.0.0.1:8092/api/domain \
  https://127.0.0.1:8095/api/domain \
  https://127.0.0.1:8010/api/erp/chat-engine \
  https://127.0.0.1:8015/api/erp/chat-engine
do
  code=$(curl -sk -o /tmp/cbody -w '%{http_code}' --connect-timeout 3 --max-time 8 "$u" || echo ERR)
  echo "$code $u  $(head -c 80 /tmp/cbody 2>/dev/null)"
done
echo '=== failed units ==='
systemctl --failed --no-pager 2>/dev/null | head -20
"""

SUP_CMD = r"""
echo '=== units ==='
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c 2>/dev/null
systemctl list-units --type=service --all 'agentlink*' --no-pager 2>/dev/null | head -40
echo '=== listen ==='
ss -lntp | grep -E ':8011|:8013|:8014|:8091|:8093|:8094' || true
echo '=== local curl ==='
for u in \
  http://127.0.0.1:8091/api/domain \
  http://127.0.0.1:8093/api/domain \
  http://127.0.0.1:8094/api/domain \
  https://127.0.0.1:8011/api/erp/chat-engine \
  https://127.0.0.1:8013/api/erp/chat-engine \
  https://127.0.0.1:8014/api/erp/chat-engine
do
  code=$(curl -sk -o /tmp/cbody -w '%{http_code}' --connect-timeout 3 --max-time 8 "$u" || echo ERR)
  echo "$code $u  $(head -c 80 /tmp/cbody 2>/dev/null)"
done
echo '=== failed units ==='
systemctl --failed --no-pager 2>/dev/null | head -20
"""


def main() -> None:
    print("===== BUYER/TENCENT =====", flush=True)
    print(run("81.70.46.119", pem=True, cmd=BUYER_CMD)[-5000:], flush=True)
    print("===== SUPPLIER/ALIYUN =====", flush=True)
    print(run("39.105.20.113", pem=False, cmd=SUP_CMD)[-5000:], flush=True)


if __name__ == "__main__":
    main()
