# -*- coding: utf-8 -*-
"""Deploy AIC peer-bind fix: platform ADP old AICs -> live cert CN from env."""
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
    "commerce/discovery.py",
    "commerce/buyer_tools/service.py",
    "commerce/flow_service.py",
    "acs/supplier-agent-a.acs.json",
    "acs/supplier-agent-b.acs.json",
    "acs/supplier-agent-c.acs.json",
    "acs/buyer-agent-a.acs.json",
    "acs/buyer-agent-b.acs.json",
    "acs/logistics-agent.acs.json",
]

SUPPLIER_FILES = [
    "acs/supplier-agent-a.acs.json",
    "acs/supplier-agent-b.acs.json",
    "acs/supplier-agent-c.acs.json",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        remote = f"/opt/agentlink/{rel}"
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=300, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", "replace")


def main() -> None:
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
    run(
        b,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
        "sleep 3; systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
        "set -a; . /opt/agentlink/.env; "
        "[ -f /etc/agentlink/buyer-a.env ] && . /etc/agentlink/buyer-a.env; set +a; "
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "import os\n"
        "from commerce.discovery import _normalize_supplier_id\n"
        "c={'aic':'1.2.156.3088.1.BUPT.2HY2P9.NH4J42.CV501K.0U11','endpoint':'https://39.105.20.113:8011/rpc','name':'采联供应商智能体A','skills':[]}\n"
        "_normalize_supplier_id(c)\n"
        "assert c['agent_id']=='supplier-a', c\n"
        "assert 'WP4OOG' in (c.get('aic') or ''), c\n"
        "print('BIND_OK', c['agent_id'], c['aic'][-28:])\n"
        "PY",
    )
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, SUPPLIER_FILES)
    run(s, "echo ACS_SYNC_OK")
    s.close()
    print("DEPLOY_AIC_PEER_BIND_DONE", flush=True)


if __name__ == "__main__":
    main()
