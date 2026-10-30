#!/bin/bash
# Python ERP 侧车：仅本机 HTTP，供 Java 反代 /api/**
set -euo pipefail
APP=/opt/agentlink
PY="${APP}/.venv/bin/python"
UV="${APP}/.venv/bin/uvicorn"

write_erp() {
  local name="$1"
  local port="$2"
  local module="$3"
  cat > "/etc/systemd/system/agentlink-${name}-erp.service" <<EOF
[Unit]
Description=AgentLink ${name} ERP sidecar (localhost HTTP)
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP}
Environment=HOST=127.0.0.1
Environment=PORT=${port}
Environment=AIP_IDENTITY_BINDING=0
EnvironmentFile=-${APP}/.env
EnvironmentFile=-/etc/agentlink/${name}.env
ExecStart=${UV} ${module} --host 127.0.0.1 --port ${port}
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/${name}-erp.log
StandardError=append:/var/log/agentlink/${name}-erp.log

[Install]
WantedBy=multi-user.target
EOF
}

cd "$APP"
$PY -m commerce.seed || true

write_erp supplier-a 18011 agents.supplier_a.main:app
write_erp supplier-b 18013 agents.supplier_b.main:app
write_erp supplier-c 18014 agents.supplier_c.main:app

systemctl daemon-reload
systemctl enable agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp
systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp
sleep 5
systemctl is-active agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp
curl -sf http://127.0.0.1:18011/health; echo
curl -sf http://127.0.0.1:18011/api/erp/conversations | head -c 200; echo
