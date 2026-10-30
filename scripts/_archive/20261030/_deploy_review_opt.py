"""Deploy DeepSeek-review optimizations (HITL/narrative/collab/cache/metrics)."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

FILES = [
    ("commerce/hitl_gate.py", "/opt/agentlink/commerce/hitl_gate.py"),
    ("commerce/amp_metrics.py", "/opt/agentlink/commerce/amp_metrics.py"),
    ("commerce/discovery.py", "/opt/agentlink/commerce/discovery.py"),
    ("commerce/flow_service.py", "/opt/agentlink/commerce/flow_service.py"),
    ("commerce/flow_routes.py", "/opt/agentlink/commerce/flow_routes.py"),
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
    _, stdout, stderr = c.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-ui-buyer; sleep 4; "
        "systemctl is-active agentlink-buyer-a agentlink-ui-buyer; "
        "python3 -c \"from commerce.hitl_gate import make_hitl; print(make_hitl('confirm_shortlist','t')['decisions'])\" "
        " 2>/dev/null || (cd /opt/agentlink && ./venv/bin/python -c "
        "\"from commerce.hitl_gate import make_hitl; print(make_hitl('confirm_shortlist','t')['decisions'])\"); "
        "curl -sk -o /dev/null -w 'ui=%{http_code}\\n' https://127.0.0.1:8090/; "
        "curl -sk http://127.0.0.1:8010/api/flow/metrics | head -c 400; echo",
        timeout=90,
        get_pty=True,
    )
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    print(out)
    if err.strip():
        print("STDERR", err)
    c.close()


if __name__ == "__main__":
    main()
