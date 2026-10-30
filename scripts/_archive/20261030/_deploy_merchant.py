# -*- coding: utf-8 -*-
"""Deploy merchant profiles + freight lane updates."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "commerce/merchant_profiles.yaml",
    "commerce/merchant.py",
    "commerce/buyer_tools/service.py",
    "commerce/buyer_routes.py",
    "commerce/flow_service.py",
    "commerce/supplier_routes.py",
    "agents/logistics/policy.yaml",
    "agents/logistics/graph.py",
    "agents/logistics/main.py",
    "agents/buyer_a/policy.yaml",
    "agents/buyer_b/policy.yaml",
    "agents/supplier_a/policy.yaml",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_c/policy.yaml",
    "agents/supplier_common/freight.py",
    "ui/static/app.js",
    "docs/merchant_profiles.md",
    "acs/buyer-agent-a.acs.json",
    "acs/buyer-agent-b.acs.json",
    "acs/logistics-agent.acs.json",
]

SUPPLIER_FILES = [
    "commerce/merchant_profiles.yaml",
    "commerce/merchant.py",
    "commerce/supplier_routes.py",
    "agents/supplier_a/policy.yaml",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_c/policy.yaml",
    "agents/supplier_common/freight.py",
    "ui/static/app.js",
    "acs/supplier-agent-a.acs.json",
    "acs/supplier-agent-b.acs.json",
    "acs/supplier-agent-c.acs.json",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = c.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> None:
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")


def main() -> None:
    print("==== Tencent ====", flush=True)
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(b, BUYER_FILES)
    run(
        b,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics; "
        "sleep 3; systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
        "curl -sk https://127.0.0.1:8010/api/erp/merchant | head -c 200; echo; "
        "curl -sk https://127.0.0.1:8012/api/erp/merchant | head -c 200; echo; "
        "curl -sk https://127.0.0.1:8015/api/erp/merchant | head -c 200; echo",
    )
    b.close()

    print("==== Aliyun ====", flush=True)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, SUPPLIER_FILES)
    run(
        s,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c "
        "agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; "
        "sleep 3; systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "curl -sk https://127.0.0.1:8011/api/erp/merchant | head -c 200; echo; "
        "curl -sk https://127.0.0.1:8013/api/erp/merchant | head -c 200; echo; "
        "curl -sk https://127.0.0.1:8014/api/erp/merchant | head -c 200; echo",
    )
    s.close()
    print("DEPLOY_MERCHANT_DONE", flush=True)


if __name__ == "__main__":
    main()
