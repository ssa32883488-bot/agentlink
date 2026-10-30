# -*- coding: utf-8 -*-
"""热修：供应入口不再拖入采购 LLM；确认工单接口恢复。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce_v2/runtime_flag.py",
    "commerce_v2/routes.py",
    "commerce_v2/llm_rewrite.py",
    "commerce_v2/rewrite_grounding.py",
    "commerce_v2/buyer_path_normal.py",
    "commerce_v2/partner_supplier.py",
    "agents/supplier_a/main.py",
    "agents/supplier_b/main.py",
    "agents/supplier_c/main.py",
    "agents/logistics/main.py",
    "agents/buyer_a/main.py",
    "agents/buyer_b/main.py",
]


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    print("$", cmd[:140], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
    text = o.read().decode("utf-8", errors="replace")
    print(text[-2000:], flush=True)
    return text


def put_files(c: paramiko.SSHClient, files: list[str]) -> None:
    with SCPClient(c.get_transport()) as scp:
        for rel in files:
            remote = f"/opt/agentlink/{rel}"
            parent = str(Path(remote).parent).replace("\\", "/")
            run(c, f"mkdir -p {parent}")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")


def main() -> None:
    print("==== supplier ====", flush=True)
    cs = connect("supplier")
    put_files(
        cs,
        [
            "commerce_v2/runtime_flag.py",
            "commerce_v2/routes.py",
            "commerce_v2/llm_rewrite.py",
            "commerce_v2/rewrite_grounding.py",
            "commerce_v2/buyer_path_normal.py",
            "commerce_v2/partner_supplier.py",
            "agents/supplier_a/main.py",
            "agents/supplier_b/main.py",
            "agents/supplier_c/main.py",
        ],
    )
    run(
        cs,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "sleep 4; systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c",
    )
    run(
        cs,
        "curl -sk https://127.0.0.1:8013/api/v2/health; echo; "
        "curl -sk https://127.0.0.1:8013/api/erp/tickets; echo; "
        "curl -sk https://127.0.0.1:8011/api/erp/tickets | head -c 120; echo",
    )
    cs.close()

    print("==== buyer ====", flush=True)
    cb = connect("buyer")
    put_files(
        cb,
        [
            "commerce_v2/runtime_flag.py",
            "commerce_v2/routes.py",
            "agents/buyer_a/main.py",
            "agents/buyer_b/main.py",
            "agents/logistics/main.py",
        ],
    )
    run(
        cb,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
        "sleep 3; systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics",
    )
    cb.close()
    print("HOTFIX_RUNTIME_DECOUPLE_DONE", flush=True)


if __name__ == "__main__":
    main()
