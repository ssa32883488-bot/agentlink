# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = c.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> None:
    _, o, e = c.exec_command(cmd, timeout=120, get_pty=True)
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")


def main() -> None:
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(
        b,
        [
            "commerce/group_mq.py",
            "commerce/flow_service.py",
            "commerce/group_routes.py",
            "agentlink_runtime/partner_app.py",
            ".env.example",
        ],
    )
    run(
        b,
        """
cd /opt/agentlink
grep -q '^ACPS_GROUP_AUCTION=' .env || echo 'ACPS_GROUP_AUCTION=1' >> .env
grep -q '^ACPS_GROUP_IDENTITY_BINDING=' .env || echo 'ACPS_GROUP_IDENTITY_BINDING=1' >> .env
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
sleep 4
systemctl is-active agentlink-buyer-a agentlink-logistics
""",
    )
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(s, ["commerce/group_mq.py", "agentlink_runtime/partner_app.py"])
    run(
        s,
        """
cd /opt/agentlink
grep -q '^ACPS_GROUP_IDENTITY_BINDING=' .env || echo 'ACPS_GROUP_IDENTITY_BINDING=1' >> .env
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 4
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
""",
    )
    s.close()
    print("deploy_p1_done", flush=True)


if __name__ == "__main__":
    main()
