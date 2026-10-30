"""Deploy platform-only ADP discovery (no local ACS fallback)."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
FILES = [
    "commerce/discovery.py",
    "commerce/chat_buyer_wit.py",
    "agents/buyer_a/AGENTS.md",
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
        for rel in FILES:
            scp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
            print("put", rel)
    _, o, _ = c.exec_command(
        "systemctl restart agentlink-buyer-a; sleep 4; "
        "systemctl is-active agentlink-buyer-a; "
        "grep -n 'platform_adp_empty\\|no supplier' /opt/agentlink/commerce/discovery.py | head -5",
        timeout=60,
        get_pty=True,
    )
    print(o.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
