"""Hotfix discovery.py + flow_service.py and smoke platform ADP."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE = r"""
systemctl restart agentlink-buyer-a
sleep 3
systemctl is-active agentlink-buyer-a
curl -sk -X POST https://127.0.0.1:8010/api/flow/cases \
  -H 'Content-Type: application/json' \
  -d '{"title":"adp-dingdang-align","brief":{"product_name":"座椅原料"}}' -o /tmp/nc.json
CID=$(python3 -c 'import json; print(json.load(open("/tmp/nc.json")).get("case_id",""))')
echo CID=$CID
curl -sk -X POST https://127.0.0.1:8010/api/flow/cases/$CID/discover \
  -H 'Content-Type: application/json' -d '{}' -o /tmp/disc.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/disc.json"))
m=d.get("discovery_meta") or {}
print("state", d.get("state"))
print("source", m.get("source"))
print("platform_error", m.get("platform_error"))
print("discovery_url", m.get("discovery_url"))
print("query", m.get("query"))
print("ncand", len(d.get("candidates") or []))
for c in (d.get("candidates") or []):
    print(" -", c.get("agent_id"), c.get("source"), c.get("name"),
          (c.get("endpoint") or "")[:55], (c.get("aic") or "")[-18:],
          (c.get("skills") or [])[:2])
PY
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(ROOT / "commerce" / "discovery.py"), "/opt/agentlink/commerce/discovery.py")
        scp.put(str(ROOT / "commerce" / "flow_service.py"), "/opt/agentlink/commerce/flow_service.py")
        print("put discovery.py + flow_service.py")
    _, stdout, _ = c.exec_command(REMOTE, timeout=180, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
