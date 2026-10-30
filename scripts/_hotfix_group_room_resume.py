# -*- coding: utf-8 -*-
"""热修：组群聊天室 AIP 挂死 → 超时回退本地 + 可续跑；并续跑卡住的 case。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

FILES = [
    "commerce_v2/buyer_path_normal.py",
    "commerce_v2/buyer_path_group.py",
    "ui/static/app.js",
    "ui/static/index.html",
]


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
        "grep -q V2_AIP_TIMEOUT_SEC /opt/agentlink/.env 2>/dev/null || echo 'V2_AIP_TIMEOUT_SEC=8' >> /opt/agentlink/.env; "
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-ui-buyer-a agentlink-ui-buyer-b; "
        "sleep 3; systemctl is-active agentlink-buyer-a; "
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "import asyncio, os\n"
        "os.environ.setdefault('AGENTLINK_RUNTIME','v2')\n"
        "os.environ.setdefault('V2_LOCAL_PARTNERS','0')\n"
        "from commerce_v2.chat_api import handle_chat\n"
        "from commerce_v2 import case_store, thread_store\n"
        "case=case_store.get_case('buyer-a','case-62d58b55')\n"
        "print('before', case and case.get('state'), len((case or {}).get('group_room',{}).get('messages') or []))\n"
        "if case and case.get('state')=='GROUP_BIDDING':\n"
        "  # bind thread if any\n"
        "  tid=thread_store.active_thread_id('buyer-a')\n"
        "  r=asyncio.run(handle_chat('buyer-a','继续组群', thread_id=tid))\n"
        "  c=r.get('case') or {}\n"
        "  room=c.get('group_room') or {}\n"
        "  print('after', c.get('state'), 'msgs', len(room.get('messages') or []), 'plans', len((room.get('summary') or {}).get('plans') or []))\n"
        "  print('reply', (r.get('reply') or '')[:120])\n"
        "else:\n"
        "  print('skip heal')\n"
        "PY"
    )
    print("$ heal...", flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=180, get_pty=True)
    print(o.read().decode("utf-8", errors="replace")[-2500:], flush=True)
    c.close()
    print("HOTFIX_GROUP_ROOM_RESUME_DONE", flush=True)


if __name__ == "__main__":
    main()
