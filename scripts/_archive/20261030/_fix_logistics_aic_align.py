# -*- coding: utf-8 -*-
"""Align LOGISTICS_AIC in .env with the live client cert CN (fixes SenderIdentityMismatch)."""
from __future__ import annotations

import os
import re
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
HOST = "81.70.46.119"

REMOTE = r"""
set -e
CERT=/opt/agentlink/certs/platform/logistics/agent-cert.pem
CN=$(openssl x509 -in "$CERT" -noout -subject | sed -n 's/.*CN *= *\([^,]*\).*/\1/p' | tr -d ' ')
echo CERT_CN=$CN
ENV_AIC=$(grep -E '^LOGISTICS_AIC=' /opt/agentlink/.env | cut -d= -f2-)
echo ENV_AIC=$ENV_AIC
ACS_AIC=$(python3 -c 'import json;print(json.load(open("/opt/agentlink/acs/logistics-agent.acs.json")).get("aic",""))')
echo ACS_AIC=$ACS_AIC
if [ -n "$CN" ] && [ "$CN" != "$ENV_AIC" ]; then
  echo ALIGNING_ENV_TO_CERT
  sed -i "s|^LOGISTICS_AIC=.*|LOGISTICS_AIC=$CN|" /opt/agentlink/.env
  python3 - <<PY
import json
p="/opt/agentlink/acs/logistics-agent.acs.json"
d=json.load(open(p,encoding="utf-8"))
d["aic"]="$CN"
json.dump(d, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
print("ACS_UPDATED")
PY
  # also patch docs mirror if present
  grep -n LOGISTICS_AIC /opt/agentlink/.env
fi
# logistics process must advertise matching AIC
if grep -q '^AGENT_AIC=' /opt/agentlink/.env; then
  echo AGENT_AIC_LINE=$(grep '^AGENT_AIC=' /opt/agentlink/.env || true)
fi
# per-unit env files?
ls /etc/systemd/system/agentlink-logistics.service
systemctl cat agentlink-logistics | sed -n '1,40p'
systemctl restart agentlink-logistics agentlink-buyer-a agentlink-buyer-b
sleep 2
systemctl is-active agentlink-logistics agentlink-buyer-a
echo DONE_ALIGN
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, e = c.exec_command(REMOTE, timeout=90)
    print((o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    main()
