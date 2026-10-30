# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

import paramiko

HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 40) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    try:
        return (o.read() + e.read()).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"[err {exc!r}]\n"


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)

    # ensure units up with latest app.py; stop domain UI only if conflicting (8091 ok)
    prep = run(
        c,
        "systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c; "
        "sleep 4; systemctl is-active agentlink-ui-supplier-b; "
        "grep -n 'erp_ok' /opt/agentlink/ui/app.py | head -5",
        timeout=50,
    )
    print("=== prep ===\n", prep, flush=True)

    smoke = run(
        c,
        r"""
set +e
echo '--- domain ---'
curl -sk -m 15 -w '\nHTTP:%{http_code}\n' https://127.0.0.1:8093/api/domain
echo '--- POST thread ---'
curl -sk -m 20 -w '\nHTTP:%{http_code}\n' -X POST https://127.0.0.1:8093/api/proxy/supplier-b/api/erp/chat/threads \
  -H 'content-type: application/json' \
  -d '{"title":"smoke-default"}'
echo '--- GET threads ---'
curl -sk -m 15 -w '\nHTTP:%{http_code}\n' https://127.0.0.1:8093/api/proxy/supplier-b/api/erp/chat/threads
echo '--- conversations ---'
curl -sk -m 15 -w '\nHTTP:%{http_code}\n' https://127.0.0.1:8093/api/proxy/supplier-b/api/erp/conversations
echo '--- deny non-erp write ---'
curl -sk -m 15 -w '\nHTTP:%{http_code}\n' -X POST https://127.0.0.1:8093/api/proxy/supplier-b/api/flow/cases \
  -H 'content-type: application/json' -d '{}'
tail -n 20 /var/log/agentlink/ui-supplier-b.log 2>/dev/null || true
""",
        timeout=90,
    )
    print("=== smoke ===\n", smoke, flush=True)
    c.close()

    if "补货请在采购商A发起" in smoke and "HTTP:403" in smoke:
        # expected only on deny non-erp; fail if on POST thread
        post_block = False
        parts = smoke.split("--- POST thread ---")
        if len(parts) > 1:
            post_section = parts[1].split("--- GET threads ---")[0]
            if "补货请在采购商A发起" in post_section:
                post_block = True
        if post_block:
            print("FAIL: ERP write still blocked", flush=True)
            return 1
    if '"domain_id"' in smoke and "HTTP:200" in smoke and ("smoke-default" in smoke or '"id"' in smoke):
        print("PASS", flush=True)
        return 0
    print("CHECK", flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
