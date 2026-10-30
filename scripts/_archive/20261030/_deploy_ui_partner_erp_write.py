# -*- coding: utf-8 -*-
"""Deploy ui/app.py to Aliyun and restart supplier/logistics UI units; smoke chat threads."""
from __future__ import annotations

import os

import paramiko
from scp import SCPClient

HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_APP = os.path.join(ROOT, "ui", "app.py")


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    with SCPClient(c.get_transport()) as scp:
        scp.put(UI_APP, "/opt/agentlink/ui/app.py")
        print("put ui/app.py", flush=True)

    _, o, e = c.exec_command(
        """
set -e
# discover ui units
systemctl list-units --type=service --all 'agentlink-ui*' --no-pager || true
ls /etc/systemd/system/agentlink-ui*.service 2>/dev/null || true
UNITS=$(ls /etc/systemd/system/agentlink-ui*.service 2>/dev/null | xargs -n1 basename | sed 's/\\.service$//' || true)
echo "UNITS=$UNITS"
for u in $UNITS; do
  case "$u" in
    *supplier*|*logistics*|*partner*) systemctl restart "$u"; echo restarted "$u";;
  esac
done
# also try common names
for u in agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c agentlink-ui-logistics agentlink-ui-supplier-domain; do
  systemctl restart "$u" 2>/dev/null && echo restarted "$u" || true
done
sleep 3
echo '--- POST threads ---'
curl -sS -w '\\nHTTP:%{http_code}\\n' -X POST http://127.0.0.1:8093/api/proxy/supplier-b/api/erp/chat/threads \
  -H 'content-type: application/json' \
  -d '{"title":"smoke-default"}'
echo '--- conversations ---'
curl -sS -w '\\nHTTP:%{http_code}\\n' http://127.0.0.1:8093/api/proxy/supplier-b/api/erp/conversations
""",
        timeout=120,
        get_pty=True,
    )
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out, flush=True)
    c.close()
    if "补货请在采购商A发起" in out:
        print("FAIL: partner write still blocked", flush=True)
        return 1
    if "HTTP:200" in out or '"id"' in out:
        print("PASS", flush=True)
        return 0
    print("CHECK", flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
