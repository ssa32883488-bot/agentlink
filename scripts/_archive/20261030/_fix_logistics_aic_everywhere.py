# -*- coding: utf-8 -*-
"""Force LOGISTICS_AIC = live logistics cert CN across env files + restart."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
HOST = "81.70.46.119"
CERT_CN = "1.2.156.3088.1.BUPT.2HY2P9.JOBNF9.39B1TM.0ALR"

REMOTE = rf"""
set -e
CN='{CERT_CN}'
for f in /opt/agentlink/.env /etc/agentlink/logistics.env /etc/agentlink/buyer-a.env /etc/agentlink/buyer-b.env /etc/agentlink/*.env; do
  [ -f "$f" ] || continue
  if grep -q '^LOGISTICS_AIC=' "$f"; then
    sed -i "s|^LOGISTICS_AIC=.*|LOGISTICS_AIC=$CN|" "$f"
    echo patched $f
  fi
done
python3 - <<'PY'
import json
p="/opt/agentlink/acs/logistics-agent.acs.json"
d=json.load(open(p,encoding="utf-8"))
d["aic"]="{CERT_CN}"
json.dump(d, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
print("acs ok", d["aic"])
PY
systemctl restart agentlink-logistics agentlink-buyer-a agentlink-buyer-b
sleep 3
pid=$(systemctl show -p MainPID --value agentlink-logistics)
echo runtime=$(tr '\0' '\n' < /proc/$pid/environ | grep '^LOGISTICS_AIC=')
systemctl is-active agentlink-logistics agentlink-buyer-a agentlink-buyer-b
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
