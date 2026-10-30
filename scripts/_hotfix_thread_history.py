# -*- coding: utf-8 -*-
"""热修：保存/查看历史对话（thread_store + API + UI），重启六体与 UI。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce_v2/thread_store.py",
    "commerce_v2/routes.py",
    "commerce_v2/partner_routes.py",
    "commerce_v2/chat_api.py",
    "ui/static/app.js",
]


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect(
            "81.70.46.119",
            username="root",
            pkey=key,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    else:
        c.connect(
            "39.105.20.113",
            username="root",
            password=PW,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str) -> None:
    print("$", cmd, flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=180, get_pty=True)
    print(o.read().decode("utf-8", errors="replace")[-2000:], flush=True)


def patch(role: str, units: str) -> None:
    print(f"==== hotfix thread_history {role} ====", flush=True)
    c = connect(role)
    app = "/opt/agentlink"
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"{app}/{rel}"
            run(c, f"mkdir -p $(dirname {remote})")
            print("put", rel, "->", remote, flush=True)
            scp.put(str(ROOT / rel), remote)
            bundle = f"/opt/agentlink_bundle/agentlink/{rel}"
            run(c, f"mkdir -p $(dirname {bundle}); cp -f {remote} {bundle} 2>/dev/null || true")
    run(c, f"systemctl restart {units}")
    run(c, f"systemctl is-active {units}")
    if role == "buyer":
        run(
            c,
            "sleep 2; "
            "curl -sk 'https://127.0.0.1:8010/api/erp/chat/threads' | head -c 300; echo; "
            "curl -sk -X POST 'https://127.0.0.1:8010/api/erp/chat/threads' "
            "-H 'Content-Type: application/json' -d '{\"title\":\"热修验证窗\"}' | head -c 300; echo",
        )
    else:
        run(
            c,
            "sleep 2; "
            "curl -sk 'https://127.0.0.1:8011/api/erp/chat/threads' | head -c 200; echo; "
            "curl -sk -X POST 'https://127.0.0.1:8011/api/erp/chat/threads' "
            "-H 'Content-Type: application/json' -d '{\"title\":\"供应验证窗\"}' | head -c 200; echo",
        )
    c.close()


def main() -> None:
    patch(
        "buyer",
        "agentlink-buyer-a agentlink-buyer-b agentlink-logistics "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics",
    )
    patch(
        "supplier",
        "agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c "
        "agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c",
    )
    print("HOTFIX_THREAD_HISTORY_DONE", flush=True)


if __name__ == "__main__":
    main()
