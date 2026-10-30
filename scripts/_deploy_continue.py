"""Deploy discovery fix + rerun evidence + bilateral assert prep."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


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
    files = [
        ("commerce/discovery.py", "/opt/agentlink/commerce/discovery.py"),
        ("scripts/demo_acps_evidence.py", "/opt/agentlink/scripts/demo_acps_evidence.py"),
        ("ui/static/app.js", "/opt/agentlink/ui/static/app.js"),
    ]
    with SCPClient(c.get_transport()) as scp:
        for local, remote in files:
            scp.put(str(ROOT / local), remote)
            print("put", local)
    _, o, _ = c.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-ui-buyer; sleep 5; "
        "systemctl is-active agentlink-buyer-a; "
        "cd /opt/agentlink && .venv/bin/python scripts/demo_acps_evidence.py; echo EXIT:$?",
        timeout=300,
        get_pty=True,
    )
    print(o.read().decode("utf-8", errors="replace"))
    with SCPClient(c.get_transport()) as scp:
        (ROOT / "docs" / "evidence").mkdir(parents=True, exist_ok=True)
        scp.get(
            "/opt/agentlink/docs/evidence/latest_pair.json",
            str(ROOT / "docs" / "evidence" / "latest_pair.json"),
        )
    print("evidence pulled")
    c.close()


if __name__ == "__main__":
    main()
