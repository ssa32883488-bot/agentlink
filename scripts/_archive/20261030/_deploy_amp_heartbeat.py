# -*- coding: utf-8 -*-
"""Deploy AMP heartbeat to both clouds and verify local NDJSON + Kafka path."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "commerce/amp_log.py",
    "agentlink_runtime/partner_app.py",
    "agents/buyer_a/main.py",
    "agents/buyer_b/main.py",
    "agents/logistics/main.py",
    ".env.example",
]
SUPPLIER_FILES = [
    "commerce/amp_log.py",
    "agentlink_runtime/partner_app.py",
]


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


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", errors="replace")


def ensure_env(c: paramiko.SSHClient) -> None:
    run(
        c,
        r"""
set -e
cd /opt/agentlink
touch .env
grep -q '^AMP_HEARTBEAT_ENABLED=' .env || echo 'AMP_HEARTBEAT_ENABLED=1' >> .env
grep -q '^AMP_HEARTBEAT_TOPIC=' .env || echo 'AMP_HEARTBEAT_TOPIC=amp.heartbeat' >> .env
grep -q '^AMP_HEARTBEAT_INTERVAL_SEC=' .env || echo 'AMP_HEARTBEAT_INTERVAL_SEC=30' >> .env
grep -q '^AMP_HEARTBEAT_FLUSH=' .env || echo 'AMP_HEARTBEAT_FLUSH=0' >> .env
grep -E 'AMP_HEARTBEAT|AMP_KAFKA' .env | head -20
""",
    )


def main() -> None:
    print("==== Tencent ====", flush=True)
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(b, BUYER_FILES)
    ensure_env(b)
    run(
        b,
        r"""
set -e
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
sleep 6
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
sleep 2
ls -la /opt/agentlink/logs/amp_heartbeat.jsonl 2>/dev/null || echo 'waiting'
wc -l /opt/agentlink/logs/amp_heartbeat.jsonl 2>/dev/null || true
tail -n 3 /opt/agentlink/logs/amp_heartbeat.jsonl 2>/dev/null || true
grep -i heartbeat /var/log/agentlink/buyer-a.log 2>/dev/null | tail -5 || true
""",
    )
    b.close()

    print("==== Aliyun ====", flush=True)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, SUPPLIER_FILES)
    ensure_env(s)
    run(
        s,
        r"""
set -e
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 6
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 2
ls -la /opt/agentlink/logs/amp_heartbeat.jsonl 2>/dev/null || echo 'waiting'
wc -l /opt/agentlink/logs/amp_heartbeat.jsonl 2>/dev/null || true
tail -n 3 /opt/agentlink/logs/amp_heartbeat.jsonl 2>/dev/null || true
""",
    )
    s.close()
    print("DEPLOY_HEARTBEAT_DONE", flush=True)


if __name__ == "__main__":
    main()
