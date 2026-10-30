# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce_v2/progress.py",
    "commerce_v2/chat_api.py",
    "commerce_v2/buyer_path_normal.py",
    "commerce_v2/buyer_path_group.py",
    "ui/static/app.js",
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
    print("$", cmd, flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
    print(o.read().decode("utf-8", errors="replace")[-1200:], flush=True)


def patch(role: str, units: str) -> None:
    print(f"==== {role} ====", flush=True)
    c = connect(role)
    app = "/opt/agentlink"
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"{app}/{rel}"
            run(c, f"mkdir -p $(dirname {remote})")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")
    run(c, f"systemctl restart {units}")
    run(c, f"systemctl is-active {units}")
    c.close()


def main() -> None:
    patch(
        "buyer",
        "agentlink-buyer-a agentlink-buyer-b agentlink-logistics "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics",
    )
    # 供应 UI 也更新 app.js（思考轨迹兼容）
    patch(
        "supplier",
        "agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c",
    )
    print("HOTFIX_PROGRESS_DONE", flush=True)


if __name__ == "__main__":
    main()
