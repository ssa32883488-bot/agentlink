# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def run(host: str, *, key: bool, cmd: str) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = {
        "hostname": host,
        "username": "root",
        "timeout": 40,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if key:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    _, o, e = c.exec_command(cmd, timeout=60, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    print("==== ALIYUN ====")
    run(
        "39.105.20.113",
        key=False,
        cmd=r"""
for u in agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; do
  echo == $u ==
  grep -E 'SSL_CERT|SSL_KEY' /etc/systemd/system/$u.service || true
done
echo --- presented ---
for p in 8011 8013 8014; do
  echo PORT $p
  echo | timeout 5 openssl s_client -connect 127.0.0.1:$p 2>/dev/null | openssl x509 -noout -subject 2>/dev/null
done
ls /etc/agentlink/tls/aic 2>/dev/null || echo no_aic_tls
""",
    )
    print("==== TENCENT ====")
    run(
        "81.70.46.119",
        key=True,
        cmd=r"""
for d in buyer-a buyer-b logistics; do
  echo == $d ==
  openssl x509 -in /opt/agentlink/certs/platform/$d/server-cert.pem -noout -subject 2>/dev/null
done
grep -E 'BUYER_A_AIC|AIP_IDENTITY|AIP_TRUST' /opt/agentlink/.env /etc/agentlink/buyer-a.env 2>/dev/null | head -20
""",
    )
