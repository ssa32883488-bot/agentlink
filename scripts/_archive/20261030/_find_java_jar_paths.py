# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import paramiko

HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(
        """
systemctl cat agentlink-supplier-a | head -50
echo '===='
ls -la /opt/agentlink/java* 2>/dev/null || true
ls -la /opt/agentlink/**/*.jar 2>/dev/null | head
find /opt/agentlink -name 'supplier-*.jar' 2>/dev/null | head -20
find /opt -name 'supplier-a*.jar' 2>/dev/null | head -10
""",
        timeout=60,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
