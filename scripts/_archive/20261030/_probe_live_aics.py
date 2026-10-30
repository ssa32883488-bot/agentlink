# -*- coding: utf-8 -*-
"""Probe live cert CNs vs env/ACS AICs on both clouds."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE = r"""
echo "=== HOST $(hostname) ==="
echo "--- certs ---"
for p in /opt/agentlink/certs/platform/*/agent-cert.pem; do
  [ -f "$p" ] || continue
  cn=$(openssl x509 -in "$p" -noout -subject 2>/dev/null | sed -n 's/.*CN *= *\([^,]*\).*/\1/p' | tr -d ' ')
  echo "$p => $cn"
done
echo "--- env ---"
grep -hE '^(SUPPLIER_[ABC]_AIC|BUYER_[AB]_AIC|LOGISTICS_AIC)=' /opt/agentlink/.env /etc/agentlink/*.env 2>/dev/null | sort -u
echo "--- acs ---"
python3 - <<'PY'
import json, glob
for p in sorted(glob.glob("/opt/agentlink/acs/*.json")):
    try:
        d = json.load(open(p, encoding="utf-8"))
        aic = d.get("aic") or ""
        print(p.split("/")[-1], aic)
    except Exception as e:
        print(p, e)
PY
"""


def run(host: str, *, pem: bool) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = {
        "hostname": host,
        "username": "root",
        "timeout": 40,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    _, o, e = c.exec_command(REMOTE, timeout=60)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    print("TENCENT")
    run("81.70.46.119", pem=True)
    print("ALIYUN")
    run("39.105.20.113", pem=False)
