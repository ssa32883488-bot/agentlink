# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
FILES = [
    "commerce/seed.py",
    "commerce/seat_catalog.py",
    "commerce/merchant_profiles.yaml",
    "agents/supplier_a/policy.yaml",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_c/policy.yaml",
]


def main() -> int:
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
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            parent = remote.rsplit("/", 1)[0]
            _, o, _ = c.exec_command(f"mkdir -p {parent}")
            o.channel.recv_exit_status()
            scp.put(str(ROOT / rel), remote)
            print("put", rel, flush=True)
    _, o, e = c.exec_command(
        """
cd /opt/agentlink
.venv/bin/python -m commerce.seed
systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp
sleep 4
curl -sf http://127.0.0.1:18011/api/erp/catalog | head -c 400; echo
curl -sk https://127.0.0.1:8011/api/erp/conversations; echo
""",
        timeout=120,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", errors="replace"), flush=True)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
