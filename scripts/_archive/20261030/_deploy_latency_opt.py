# -*- coding: utf-8 -*-
"""Deploy parallel invite + early abort + parallel RPC auction latency opts."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = c.open_sftp()
    for rel in ("commerce/flow_service.py", "commerce/group_mq.py"):
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()
    # env knobs (idempotent append if missing)
    env_bits = (
        "grep -q ACPS_GROUP_INVITE_TIMEOUT_SEC /opt/agentlink/.env || "
        "echo 'ACPS_GROUP_INVITE_TIMEOUT_SEC=5' >> /opt/agentlink/.env; "
        "grep -q ACPS_GROUP_MIN_SUPPLIERS /opt/agentlink/.env || "
        "echo 'ACPS_GROUP_MIN_SUPPLIERS=2' >> /opt/agentlink/.env; "
        "grep -q ACPS_GROUP_BID_WAIT_SEC /opt/agentlink/.env || "
        "echo 'ACPS_GROUP_BID_WAIT_SEC=12' >> /opt/agentlink/.env; "
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
        "sleep 4; systemctl is-active agentlink-buyer-a agentlink-logistics"
    )
    _, o, e = c.exec_command(env_bits, timeout=90, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()
    print("DEPLOY_LATENCY_OPT_DONE", flush=True)


if __name__ == "__main__":
    main()
