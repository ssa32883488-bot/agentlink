# -*- coding: utf-8 -*-
"""热修：切页回灌对话历史；双方确认后提醒建立物流单。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "ui/static/app.js",
    "commerce_v2/order_sync.py",
    "commerce_v2/gates.py",
    "commerce_v2/routes.py",
]
SUP_FILES = [
    "commerce_v2/order_sync.py",
    "commerce_v2/gates.py",
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


def run(c: paramiko.SSHClient, cmd: str) -> None:
    print("$", cmd[:140], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
    print(o.read().decode("utf-8", errors="replace")[-1800:], flush=True)


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    with SCPClient(c.get_transport()) as scp:
        for rel in files:
            remote = f"/opt/agentlink/{rel}"
            parent = str(Path(remote).parent).replace("\\", "/")
            run(c, f"mkdir -p {parent}")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")


def main() -> None:
    cb = connect("buyer")
    put(cb, BUYER_FILES)
    run(
        cb,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics; "
        "sleep 3; systemctl is-active agentlink-buyer-a agentlink-ui-buyer-a",
    )
    cb.close()

    cs = connect("supplier")
    put(cs, SUP_FILES)
    run(
        cs,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c "
        "agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; "
        "sleep 3; systemctl is-active agentlink-supplier-b agentlink-ui-supplier-b",
    )
    cs.close()
    print("HOTFIX_CHAT_HISTORY_LOGISTICS_DONE", flush=True)


if __name__ == "__main__":
    main()
