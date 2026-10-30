# -*- coding: utf-8 -*-
"""推送议价满减/方案相关文件到双云并重启供应+采购服务。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "agents/supplier_common/promo.py",
    "agents/supplier_common/negotiate.py",
    "agents/supplier_a/policy.yaml",
    "agents/supplier_a/graph.py",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_b/graph.py",
    "agents/supplier_c/policy.yaml",
    "agents/supplier_c/graph.py",
    "commerce/scheme_planner.py",
    "commerce/flow_service.py",
    "commerce/chat_buyer_wit.py",
    "docs/design_bargain_promo_schemes.md",
    "docs/design_procurement_dialogue_flow.md",
    "docs/evidence/bargain_promo_schemes_test.md",
    "scripts/_smoke_bargain_schemes.py",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        local = ROOT / rel
        if not local.is_file():
            print("skip missing", rel, flush=True)
            continue
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = c.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(local), remote)
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", errors="replace")


def main() -> int:
    print("==== tencent ====", flush=True)
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
    put(b, FILES)
    run(
        b,
        """
set -e
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics || true
sleep 2
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
cd /opt/agentlink && /opt/agentlink/.venv/bin/python scripts/_smoke_bargain_schemes.py
""",
    )
    b.close()

    print("==== aliyun ====", flush=True)
    a = paramiko.SSHClient()
    a.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    a.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(a, FILES)
    run(
        a,
        """
set -e
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 3
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
cd /opt/agentlink
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
$PY scripts/_smoke_bargain_schemes.py
""",
    )
    a.close()
    print("DEPLOY_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
