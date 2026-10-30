# -*- coding: utf-8 -*-
"""热修：组群聊天室「收起」不被 4s 轮询强弹。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
FILES = ["ui/static/app.js", "ui/static/index.html", "ui/static/styles.css"]


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)

    def run(cmd: str) -> None:
        print("$", cmd[:140], flush=True)
        _i, o, _e = c.exec_command(cmd, timeout=60, get_pty=True)
        print(o.read().decode("utf-8", errors="replace")[-1200:], flush=True)

    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            run(f"mkdir -p {Path(remote).parent.as_posix()}")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")

    run(
        "grep -n 'groupRoomCollapsed\\|group-room-collapse3\\|groupRoomReopen' "
        "/opt/agentlink/ui/static/app.js /opt/agentlink/ui/static/index.html | head -30"
    )
    print("UI_COLLAPSE_HOTFIX_DONE", flush=True)
    c.close()


if __name__ == "__main__":
    main()
