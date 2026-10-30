# -*- coding: utf-8 -*-
"""Deploy Group P0 to Tencent (buyer/logistics) + Aliyun (suppliers); set MQ env; restart."""
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
    "commerce/group_mq.py",
    "commerce/group_routes.py",
    "commerce/buyer_routes.py",
    "agentlink_runtime/partner_app.py",
    ".env.example",
]
SUPPLIER_FILES = [
    "commerce/group_mq.py",
    "agentlink_runtime/partner_app.py",
    ".env.example",
]

MQ_ENV = [
    "ACPS_MQ_HOST=wt.ioa.pub",
    "ACPS_MQ_PORT=5671",
    "ACPS_MQ_VHOST=acps",
    "ACPS_MQ_AUTH_URL=https://wt.ioa.pub/mq-auth",
    "ACPS_GROUP_IDENTITY_BINDING=1",
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
    _, o, e = c.exec_command(cmd, timeout=240, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", errors="replace")


def ensure_mq_env(c: paramiko.SSHClient) -> None:
    lines = "\n".join(
        f"grep -q '^{k.split('=')[0]}=' .env || echo '{k}' >> .env"
        for k in MQ_ENV
    )
    # force vhost=acps if wrongly set to /
    run(
        c,
        f"""
set -e
cd /opt/agentlink
touch .env
{lines}
sed -i 's|^ACPS_MQ_VHOST=/.*|ACPS_MQ_VHOST=acps|' .env || true
grep -E '^ACPS_MQ_' .env | head -20
""",
    )


def main() -> None:
    print("==== Tencent buyer/logistics ====", flush=True)
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
    ensure_mq_env(b)
    run(
        b,
        r"""
set -e
cd /opt/agentlink
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics 2>/dev/null || \
  (pkill -f 'agents.buyer_a' || true; pkill -f 'agents.logistics' || true; sleep 1;
   nohup /opt/agentlink/.venv/bin/python -m agents.buyer_a.main >/tmp/buyer-a.log 2>&1 &
   nohup /opt/agentlink/.venv/bin/python -m agents.logistics.main >/tmp/logistics.log 2>&1 &)
sleep 2
curl -sk https://127.0.0.1:8010/health || curl -s http://127.0.0.1:8010/health || true
curl -sk https://127.0.0.1:8015/health || curl -s http://127.0.0.1:8015/health || true
curl -sk -X POST https://127.0.0.1:8015/group/join -H 'content-type: application/json' -d '{}' | head -c 200 || true
""",
    )
    b.close()

    print("==== Aliyun suppliers ====", flush=True)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        s.connect(
            SUPPLIER,
            username="root",
            pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
            timeout=40,
            allow_agent=False,
            look_for_keys=False,
        )
    except Exception:
        s.connect(
            SUPPLIER,
            username="root",
            password=PW,
            timeout=40,
            allow_agent=False,
            look_for_keys=False,
        )
    put(s, SUPPLIER_FILES)
    ensure_mq_env(s)
    run(
        s,
        r"""
set -e
cd /opt/agentlink
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c 2>/dev/null || \
  (pkill -f 'agents.supplier_' || true; sleep 1;
   nohup /opt/agentlink/.venv/bin/python -m agents.supplier_a.main >/tmp/sa.log 2>&1 &
   nohup /opt/agentlink/.venv/bin/python -m agents.supplier_b.main >/tmp/sb.log 2>&1 &
   nohup /opt/agentlink/.venv/bin/python -m agents.supplier_c.main >/tmp/sc.log 2>&1 &)
sleep 2
for p in 8011 8013 8014; do curl -sk https://127.0.0.1:$p/health || curl -s http://127.0.0.1:$p/health || true; echo; done
""",
    )
    s.close()
    print("deploy done", flush=True)


if __name__ == "__main__":
    main()
