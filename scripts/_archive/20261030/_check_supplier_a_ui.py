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
        r"""
set +e
echo '=== unit ==='
systemctl is-active agentlink-ui-supplier-a agentlink-supplier-a agentlink-supplier-a-erp
grep -E 'ExecStart|UI_PORT|ssl' /etc/systemd/system/agentlink-ui-supplier-a.service
echo '=== http vs https ==='
curl -sS -m 5 -o /dev/null -w 'http:%{http_code}\n' http://127.0.0.1:8091/ || echo http_fail
curl -sk -m 5 -o /dev/null -w 'https:%{http_code}\n' https://127.0.0.1:8091/ || echo https_fail
echo '=== domain/catalog via UI proxy ==='
curl -sk -m 8 https://127.0.0.1:8091/api/domain | head -c 220; echo
curl -sk -m 8 https://127.0.0.1:8091/api/proxy/supplier-a/api/erp/catalog | python3 -c 'import sys,json; d=json.load(sys.stdin); items=d.get("items") or [];
print("items",len(items));
print([(i.get("code"),i.get("list_price"),i.get("floor_price")) for i in items[:3]])'
curl -sk -m 8 -X POST https://127.0.0.1:8091/api/proxy/supplier-a/api/erp/chat/threads -H 'content-type: application/json' -d '{"title":"ui-check"}' | head -c 180; echo
""",
        timeout=60,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", errors="replace"), flush=True)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
