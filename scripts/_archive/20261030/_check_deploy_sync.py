# -*- coding: utf-8 -*-
"""Compare local key files vs dual-cloud /opt/agentlink."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

TENCENT_FILES = [
    "commerce/discovery.py",
    "commerce/buyer_tools/service.py",
    "commerce/flow_service.py",
    "commerce/seat_catalog.py",
    "ui/static/app.js",
    "acs/supplier-agent-a.acs.json",
    "acs/supplier-agent-c.acs.json",
]
ALIYUN_FILES = [
    "acs/supplier-agent-a.acs.json",
    "commerce/seat_catalog.py",
    "agents/supplier_common/catalog_price.py",
]


def md5_local(rel: str) -> str | None:
    p = ROOT / rel
    return hashlib.md5(p.read_bytes()).hexdigest() if p.is_file() else None


def check(host: str, *, pem: bool, files: list[str], label: str, extra: str) -> None:
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
    print(f"== {label} ==")
    sftp = c.open_sftp()
    for rel in files:
        local = md5_local(rel)
        remote_path = f"/opt/agentlink/{rel}"
        try:
            data = sftp.file(remote_path, "r").read()
            remote = hashlib.md5(data).hexdigest()
        except OSError:
            remote = None
        mark = "OK" if local and remote and local == remote else "DIFF"
        print(f"  {mark} {rel}")
        if mark == "DIFF":
            print(f"       local={local} remote={remote}")
    sftp.close()
    _, o, e = c.exec_command(extra, timeout=60)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


TENCENT_EXTRA = r"""
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
echo --- AIC env ---
grep -E '^SUPPLIER_[ABC]_AIC=|^BUYER_A_AIC=|^LOGISTICS_AIC=' /etc/agentlink/buyer-a.env | sed 's/\(.*\.=.*\.\.\.\)/\1/' 
grep -E '^SUPPLIER_[ABC]_AIC=|^BUYER_A_AIC=|^LOGISTICS_AIC=' /etc/agentlink/buyer-a.env
"""

ALIYUN_EXTRA = r"""
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
echo --- Java TLS CN ---
for port in 8011 8013 8014; do
  echo -n "port $port: "
  echo | timeout 5 openssl s_client -connect 127.0.0.1:$port 2>/dev/null | openssl x509 -noout -subject 2>/dev/null | sed -n 's/.*CN *= *\([^,]*\).*/\1/p'
done
echo --- Java SSL_CERT unit ---
grep SSL_CERT /etc/systemd/system/agentlink-supplier-a.service
"""


if __name__ == "__main__":
    check("81.70.46.119", pem=True, files=TENCENT_FILES, label="TENCENT", extra=TENCENT_EXTRA)
    check("39.105.20.113", pem=False, files=ALIYUN_FILES, label="ALIYUN", extra=ALIYUN_EXTRA)
