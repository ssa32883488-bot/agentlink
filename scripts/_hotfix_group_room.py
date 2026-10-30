# -*- coding: utf-8 -*-
"""热修：组群竞价置顶聊天室 + 可选物流 + 国标 Group + 可拆单。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER = [
    "commerce_v2/group_room.py",
    "commerce_v2/buyer_path_group.py",
    "commerce_v2/ask_user.py",
    "commerce_v2/chat_api.py",
    "ui/static/app.js",
    "ui/static/index.html",
    "ui/static/styles.css",
]
SUP = [
    "commerce_v2/group_room.py",
    "commerce_v2/ask_user.py",
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
    print(o.read().decode("utf-8", errors="replace")[-1600:], flush=True)


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    with SCPClient(c.get_transport()) as scp:
        for rel in files:
            remote = f"/opt/agentlink/{rel}"
            run(c, f"mkdir -p {Path(remote).parent.as_posix()}")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")


def main() -> None:
    cb = connect("buyer")
    put(cb, BUYER)
    # 默认尝试国标 Group
    run(
        cb,
        "grep -q V2_TRY_GROUP_MQ /opt/agentlink/.env 2>/dev/null || echo 'V2_TRY_GROUP_MQ=1' >> /opt/agentlink/.env; "
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b agentlink-ui-logistics; sleep 3; "
        "systemctl is-active agentlink-buyer-a agentlink-ui-buyer-a; "
        "grep -n 'group-room-modal\\|groupRoomModal' /opt/agentlink/ui/static/index.html | head -5",
    )
    cb.close()

    cs = connect("supplier")
    put(cs, SUP)
    run(
        cs,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "sleep 2; systemctl is-active agentlink-supplier-b",
    )
    cs.close()
    print("HOTFIX_GROUP_ROOM_DONE", flush=True)


if __name__ == "__main__":
    main()
