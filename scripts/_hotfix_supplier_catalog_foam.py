# -*- coding: utf-8 -*-
"""供应云同步含坐垫的 catalog + inventory 接口。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
FILES = ["commerce_v2/catalog.py", "commerce_v2/partner_routes.py"]


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )

    def run(cmd: str) -> None:
        print("$", cmd[:120], flush=True)
        _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
        print(o.read().decode("utf-8", errors="replace")[-1500:], flush=True)

    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            run(f"mkdir -p $(dirname {remote})")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")
    run(
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "sleep 3; systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c"
    )
    c.close()
    print("SUPPLIER_CATALOG_FOAM_DONE", flush=True)


if __name__ == "__main__":
    main()
