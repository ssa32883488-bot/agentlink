# -*- coding: utf-8 -*-
"""Deploy table-first Wit prompts to Tencent buyers + Aliyun suppliers."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce/chat_buyer_wit.py",
    "commerce/chat_supplier_wit.py",
]


def put(c: paramiko.SSHClient, rels: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in rels:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def main() -> None:
    print("==== TENCENT ====", flush=True)
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
    print(
        run(
            b,
            "grep -n '表格优先' /opt/agentlink/commerce/chat_buyer_wit.py /opt/agentlink/commerce/chat_supplier_wit.py; "
            "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 4; "
            "systemctl is-active agentlink-buyer-a agentlink-buyer-b; "
            "curl -sk https://127.0.0.1:8010/health; echo; curl -sk https://127.0.0.1:8012/health; echo",
        ),
        flush=True,
    )
    b.close()

    print("==== ALIYUN ====", flush=True)
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
    put(s, FILES)
    # supplier chat is via ERP sidecars / UI proxy — restart ERP + ensure file present
    print(
        run(
            s,
            "grep -n '表格优先' /opt/agentlink/commerce/chat_supplier_wit.py; "
            "systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp 2>/dev/null || true; "
            "systemctl is-active agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp 2>/dev/null || true; "
            "echo DEPLOY_TABLE_PROMPTS_OK",
        ),
        flush=True,
    )
    s.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
