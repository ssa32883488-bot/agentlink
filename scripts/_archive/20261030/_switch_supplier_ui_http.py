# -*- coding: utf-8 -*-
"""Switch Aliyun supplier UI units from HTTPS to plain HTTP (agent AIP stays HTTPS)."""
from __future__ import annotations

import os
import textwrap

import paramiko

HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE = textwrap.dedent(
    r"""
set -e
write_ui() {
  local name="$1" port="$2" cfg="$3"
  cat > "/etc/systemd/system/agentlink-ui-${name}.service" <<EOF
[Unit]
Description=AgentLink UI ${name}
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/agentlink
EnvironmentFile=-/opt/agentlink/.env
Environment=HOST=0.0.0.0
Environment=UI_PORT=${port}
Environment=UI_HTTPX_VERIFY=0
Environment=AGENTLINK_UI_CONFIG=/opt/agentlink/ui/${cfg}
ExecStart=/opt/agentlink/.venv/bin/python -m uvicorn ui.app:app --host 0.0.0.0 --port ${port}
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/ui-${name}.log
StandardError=append:/var/log/agentlink/ui-${name}.log

[Install]
WantedBy=multi-user.target
EOF
}

write_ui supplier-a 8091 config_supplier_a.yaml
write_ui supplier-b 8093 config_supplier_b.yaml
write_ui supplier-c 8094 config_supplier_c.yaml

systemctl daemon-reload
systemctl restart agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
sleep 3
systemctl is-active agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
echo '--- probe ---'
curl -sS -m 8 -o /dev/null -w 'a_http:%{http_code}\n' http://127.0.0.1:8091/
curl -sS -m 8 -o /dev/null -w 'b_http:%{http_code}\n' http://127.0.0.1:8093/
curl -sS -m 8 -o /dev/null -w 'c_http:%{http_code}\n' http://127.0.0.1:8094/
curl -sS -m 8 http://127.0.0.1:8091/api/domain | head -c 180; echo
curl -sS -m 8 http://127.0.0.1:8091/api/proxy/supplier-a/api/erp/catalog | python3 -c 'import sys,json; d=json.load(sys.stdin); print("catalog",len(d.get("items") or []))'
curl -sS -m 8 -X POST http://127.0.0.1:8091/api/proxy/supplier-a/api/erp/chat/threads -H 'content-type: application/json' -d '{"title":"http-ui"}' | head -c 160; echo
"""
)


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(REMOTE, timeout=90, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out, flush=True)
    c.close()
    if "a_http:200" in out and "catalog" in out:
        print("PASS", flush=True)
        return 0
    print("FAIL", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
