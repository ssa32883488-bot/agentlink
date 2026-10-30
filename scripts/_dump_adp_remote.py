"""Dump raw ADP response from buyer host with .env loaded."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE = r"""
set -a
. /opt/agentlink/.env
set +a
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import os, json, httpx
base = os.environ.get("ACPS_DISCOVERY_URL","").rstrip("/")
print("base", base)
url = base + "/acps-adp-v2/discover"
for q in ["采联供应商智能体 报价 议价 agentlink", "需要供应「座椅」的工业品供应商，可报价议价"]:
    r = httpx.post(url, json={"type":"explicit","query":q,"limit":10}, timeout=30)
    print("====", q, r.status_code)
    d = r.json()
    res = d.get("result") or {}
    acs_map = res.get("acsMap") or {}
    print("acsMap", len(acs_map), "agents_groups", len(res.get("agents") or []))
    for aic, acs in acs_map.items():
        name = acs.get("name","")
        ep = ((acs.get("endPoints") or [{}])[0] or {}).get("url","")
        mark = ""
        if any(x in aic for x in ("NH4J42","SHDUXP","8R39K3","ODIFWZ","ZBD999","21P09A")):
            mark = " <<OURS"
        if "供应商" in name or "采联" in name or mark:
            print(f"  {name} | {aic[-22:]} | {ep}{mark}")
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
    _, stdout, _ = c.exec_command(REMOTE, timeout=120, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
