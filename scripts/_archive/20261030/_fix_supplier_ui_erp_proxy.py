# -*- coding: utf-8 -*-
"""修复供应控制台 404：启 Python ERP 侧车 + 更新 Java jar（反代 /api/**）并重启。"""
from __future__ import annotations

import os
import ssl
import sys
import urllib.request
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
HOST = "39.105.20.113"
CTX = ssl._create_unverified_context()
JARS = [
    ("supplier-a", "java-suppliers/supplier-a/build/libs/supplier-a-0.1.0.jar"),
    ("supplier-b", "java-suppliers/supplier-b/build/libs/supplier-b-0.1.0.jar"),
    ("supplier-c", "java-suppliers/supplier-c/build/libs/supplier-c-0.1.0.jar"),
]


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=45, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 300) -> str:
    print(">>>", cmd[:220], flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out[-10000:], flush=True)
    code = o.channel.recv_exit_status()
    if code != 0:
        raise SystemExit(f"remote exit {code}")
    return out


def main() -> int:
    for _, rel in JARS:
        if not (ROOT / rel).is_file():
            raise SystemExit(f"missing {rel}; rebuild jars first")

    c = connect()
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(ROOT / "scripts/_remote_enable_supplier_erp_sidecar.sh"), "/tmp/_erp_sidecar.sh")
        for name, rel in JARS:
            scp.put(str(ROOT / rel), f"/opt/agentlink/java-suppliers/{name}.jar")
            print("put jar", name, flush=True)

    run(c, "sed -i 's/\\r$//' /tmp/_erp_sidecar.sh; chmod +x /tmp/_erp_sidecar.sh; bash /tmp/_erp_sidecar.sh")

    # inject ERP_UPSTREAM into java units if missing
    run(
        c,
        r"""
set -e
patch_unit() {
  local name=$1 port=$2
  local f=/etc/systemd/system/agentlink-${name}.service
  if ! grep -q ERP_UPSTREAM "$f"; then
    sed -i "/Environment=SSL_KEY=/a Environment=ERP_UPSTREAM=http://127.0.0.1:${port}" "$f"
  fi
}
patch_unit supplier-a 18011
patch_unit supplier-b 18013
patch_unit supplier-c 18014
systemctl daemon-reload
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for i in $(seq 1 60); do
  if curl -skf https://127.0.0.1:8011/health >/dev/null; then break; fi
  sleep 2
done
curl -sk https://127.0.0.1:8011/health; echo
curl -sk https://127.0.0.1:8011/api/erp/conversations | head -c 300; echo
curl -sk https://127.0.0.1:8011/api/erp/catalog | head -c 300; echo
""",
        timeout=240,
    )
    c.close()

    # public smoke
    url = f"https://{HOST}:8011/api/erp/conversations"
    raw = urllib.request.urlopen(url, context=CTX, timeout=30).read().decode()
    print("PUBLIC", url, raw[:300], flush=True)
    if "items" not in raw and "404" in raw:
        print("FAIL", flush=True)
        return 1
    print("PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
