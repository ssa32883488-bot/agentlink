# -*- coding: utf-8 -*-
"""热修：组群断点① 无处可点 — 短名单按钮改为「确认组群竞价」。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
FILES = ["ui/static/app.js", "commerce_v2/buyer_path_group.py"]


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            print("put", rel, flush=True)
            _i, o, _e = c.exec_command(f"mkdir -p {Path(remote).parent.as_posix()}", timeout=30)
            o.read()
            scp.put(str(ROOT / rel), remote)
            _i, o, _e = c.exec_command(
                f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true", timeout=30
            )
            o.read()
    cmd = (
        "systemctl restart agentlink-buyer-a agentlink-buyer-b "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b; sleep 2; "
        "systemctl is-active agentlink-buyer-a agentlink-ui-buyer-a; "
        "grep -n '确认组群竞价\\|group_ask' /opt/agentlink/ui/static/app.js | head -15"
    )
    print("$", cmd[:120], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=90, get_pty=True)
    print(o.read().decode("utf-8", errors="replace")[-2000:], flush=True)
    c.close()
    print("HOTFIX_GROUP_ASK_BUTTON_DONE", flush=True)


if __name__ == "__main__":
    main()
