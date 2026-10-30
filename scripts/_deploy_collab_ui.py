"""Hot-patch collab UI + Wit onto buyer host."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
HOST, USER = "81.70.46.119", "root"

FILES = [
    ("ui/static/app.js", "/opt/agentlink/ui/static/app.js"),
    ("ui/static/styles.css", "/opt/agentlink/ui/static/styles.css"),
    ("ui/static/index.html", "/opt/agentlink/ui/static/index.html"),
    ("commerce/chat_buyer_wit.py", "/opt/agentlink/commerce/chat_buyer_wit.py"),
]


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST,
        username=USER,
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    with SCPClient(c.get_transport()) as scp:
        for local, remote in FILES:
            p = ROOT / local
            assert p.is_file(), local
            scp.put(str(p), remote)
            print("put", local, "->", remote)

    cmd = (
        "systemctl restart agentlink-buyer-a agentlink-ui-buyer; sleep 3; "
        "systemctl is-active agentlink-buyer-a agentlink-ui-buyer; "
        "curl -sk -o /dev/null -w 'ui=%{http_code}\\n' https://127.0.0.1:8090/; "
        "curl -sk 'https://127.0.0.1:8090/api/agents/buyer-a/interactions?limit=3'; "
        "echo; "
        "grep -n '多智能体协作\\|loadCollab\\|collab-hop' "
        "/opt/agentlink/ui/static/index.html /opt/agentlink/ui/static/app.js | head -20; "
        "grep -n '多智能体可见性' /opt/agentlink/commerce/chat_buyer_wit.py | head -5"
    )
    _, stdout, stderr = c.exec_command(cmd, timeout=90, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err:
        print(err[-800:], file=sys.stderr)
    c.close()


if __name__ == "__main__":
    main()
