"""Force supplier UI to disable httpx SSL verify; restart and probe health."""
from __future__ import annotations

import os
import sys

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
REMOTE = "/tmp/fix_ui_httpx_verify.sh"
SCRIPT = r"""#!/bin/bash
set -e
cd /opt/agentlink
echo '== .env UI_HTTPX =='
grep UI_HTTPX .env || echo none
# remove conflicting override if present
sed -i '/^UI_HTTPX_VERIFY=/d' .env || true
echo 'UI_HTTPX_VERIFY=0' >> .env
CRT=/etc/agentlink/tls/server.crt
KEY=/etc/agentlink/tls/server.key
if [ ! -f "$CRT" ]; then
  CRT=/opt/agentlink/certs/platform/supplier-a/server-cert.pem
  KEY=/opt/agentlink/certs/platform/supplier-a/server-key.pem
fi
cat >/etc/systemd/system/agentlink-ui-supplier.service <<EOF
[Unit]
Description=AgentLink UI ui-supplier
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/agentlink
EnvironmentFile=-/opt/agentlink/.env
Environment=HOST=0.0.0.0
Environment=UI_PORT=8091
Environment=UI_HTTPX_VERIFY=0
Environment=AGENTLINK_UI_CONFIG=/opt/agentlink/ui/config_supplier_domain.yaml
ExecStart=/opt/agentlink/.venv/bin/python -m uvicorn ui.app:app --host 0.0.0.0 --port 8091 --ssl-certfile ${CRT} --ssl-keyfile ${KEY}
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/ui-supplier.log
StandardError=append:/var/log/agentlink/ui-supplier.log

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl restart agentlink-ui-supplier
sleep 3
systemctl is-active agentlink-ui-supplier
echo '== process env =='
PID=$(systemctl show -p MainPID --value agentlink-ui-supplier)
tr '\0' '\n' < /proc/$PID/environ | grep UI_HTTPX || true
echo '== health =='
curl -sk https://127.0.0.1:8091/api/agents/supplier-a/health; echo
curl -sk https://127.0.0.1:8091/api/agents/supplier-b/health; echo
curl -sk https://127.0.0.1:8091/api/agents/supplier-c/health; echo
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "39.105.20.113",
        username="root",
        password=PW,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = c.open_sftp()
    with sftp.file(REMOTE, "w") as f:
        f.write(SCRIPT)
    sftp.close()
    _, o, _ = c.exec_command(f"bash {REMOTE}", timeout=90, get_pty=True)
    sys.stdout.buffer.write(o.read() + b"\n")
    c.close()


if __name__ == "__main__":
    main()
