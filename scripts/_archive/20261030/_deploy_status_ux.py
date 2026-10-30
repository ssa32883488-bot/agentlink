"""Deploy realtime chat status UX to buyer host."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

FILES = [
    ("commerce/progress.py", "/opt/agentlink/commerce/progress.py"),
    ("commerce/discovery.py", "/opt/agentlink/commerce/discovery.py"),
    ("commerce/flow_service.py", "/opt/agentlink/commerce/flow_service.py"),
    ("commerce/chat_buyer_wit.py", "/opt/agentlink/commerce/chat_buyer_wit.py"),
    ("ui/static/app.js", "/opt/agentlink/ui/static/app.js"),
    ("ui/static/styles.css", "/opt/agentlink/ui/static/styles.css"),
]


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    with SCPClient(c.get_transport()) as scp:
        for local, remote in FILES:
            scp.put(str(ROOT / local), remote)
            print("put", local)
    _, stdout, _ = c.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-ui-buyer; sleep 3; "
        "systemctl is-active agentlink-buyer-a agentlink-ui-buyer; "
        "grep -n 'think-trail\\|pushThinkStep' /opt/agentlink/ui/static/app.js | head -5; "
        "grep -n 'make_queue_reporter\\|正在梧桐平台' /opt/agentlink/commerce/chat_buyer_wit.py | head -8; "
        "curl -sk -o /dev/null -w 'ui=%{http_code}\\n' https://127.0.0.1:8090/",
        timeout=60,
        get_pty=True,
    )
    print(stdout.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
