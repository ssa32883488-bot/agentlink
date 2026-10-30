# -*- coding: utf-8 -*-
"""热修供应/物流 Partner 兼容桩 + UI，重启服务。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
FILES = [
    "commerce_v2/partner_routes.py",
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
    print(o.read().decode("utf-8", errors="replace")[-1500:], flush=True)


def patch(role: str, units: str, ui_units: str) -> None:
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
    run(c, f"systemctl restart {ui_units}")
    run(c, f"systemctl is-active {units} {ui_units}")
    c.close()


def main() -> None:
    patch(
        "supplier",
        "agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c",
        "agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c",
    )
    patch(
        "buyer",
        "agentlink-logistics",
        "agentlink-ui-logistics agentlink-ui-buyer-a agentlink-ui-buyer-b",
    )
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
