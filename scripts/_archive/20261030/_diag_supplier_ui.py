# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

import paramiko

HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 25) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    try:
        data = o.read() + e.read()
    except Exception as exc:  # noqa: BLE001
        try:
            o.channel.close()
        except Exception:
            pass
        return f"[timeout/err {exc!r}]\n"
    return data.decode("utf-8", errors="replace")


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)

    chunks = []
    chunks.append("=== unit file b ===\n" + run(c, "cat /etc/systemd/system/agentlink-ui-supplier-b.service"))
    chunks.append("=== unit file supplier ===\n" + run(c, "cat /etc/systemd/system/agentlink-ui-supplier.service 2>/dev/null || echo none"))
    chunks.append("=== ports ===\n" + run(c, "ss -lntp | grep -E '809[0-5]|801[0-5]' || echo no-ports"))
    chunks.append("=== procs ===\n" + run(c, "ps aux | grep -E '[u]i.app|[u]vicorn' || echo no-proc"))
    chunks.append(
        "=== stop conflicting ===\n"
        + run(
            c,
            "systemctl stop agentlink-ui-supplier 2>/dev/null; systemctl disable agentlink-ui-supplier 2>/dev/null; "
            "systemctl restart agentlink-ui-supplier-b; sleep 3; "
            "systemctl is-active agentlink-ui-supplier-b; "
            "ss -lntp | grep 8093 || echo '8093 not listening'",
            timeout=40,
        )
    )
    chunks.append(
        "=== curl domain ===\n"
        + run(c, "timeout 8 curl -sS -m 6 -w '\\nHTTP:%{http_code}\\n' http://127.0.0.1:8093/api/domain || echo curl_fail")
    )
    chunks.append(
        "=== manual python import ===\n"
        + run(
            c,
            "cd /opt/agentlink; .venv/bin/python -c \"from ui import app; print('import_ok', app.CFG.get('domain_id'))\"",
            timeout=30,
        )
    )
    chunks.append(
        "=== journal ===\n"
        + run(c, "journalctl -u agentlink-ui-supplier-b -n 40 --no-pager -o cat")
    )
    text = "\n".join(chunks)
    sys.stdout.write(text)
    sys.stdout.flush()
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
