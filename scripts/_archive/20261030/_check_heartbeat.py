# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def run(c, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=60)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    sys.stdout.write(out)
    return out


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
    print("==== BUYER HOST ====")
    run(
        b,
        r"""
ls -la /opt/agentlink/logs/ 2>/dev/null | head -40
echo '--- heartbeat files ---'
ls -la /opt/agentlink/logs/*heartbeat* 2>/dev/null || echo no_heartbeat_log_files
echo '--- code grep ---'
grep -RIn --include='*.py' -E 'HeartbeatEmitter|amp_heartbeat|agent\.Heartbeat|Heartbeat\(' \
  /opt/agentlink/agentlink_runtime /opt/agentlink/commerce /opt/agentlink/agents /opt/agentlink/scripts 2>/dev/null | head -30 || true
echo '--- amp_log mentions ---'
grep -n -E 'heartbeat|Heartbeat' /opt/agentlink/commerce/amp_log.py 2>/dev/null || echo amp_log_no_heartbeat
echo '--- env ---'
grep -E 'HEART|AMP_' /opt/agentlink/.env 2>/dev/null | head -20 || true
""",
    )
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    print("==== SUPPLIER HOST ====")
    run(
        s,
        r"""
ls -la /opt/agentlink/logs/*heartbeat* 2>/dev/null || echo no_heartbeat_log_files
grep -RIn --include='*.py' -E 'HeartbeatEmitter|amp_heartbeat|agent\.Heartbeat' \
  /opt/agentlink/agentlink_runtime /opt/agentlink/commerce /opt/agentlink/agents 2>/dev/null | head -20 || true
""",
    )
    s.close()


if __name__ == "__main__":
    main()
