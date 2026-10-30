"""Debug platform discover + local fill on buyer host."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE_PY = r"""
import asyncio, sys
sys.path.insert(0, "/opt/agentlink")
from commerce.discovery import discover_suppliers, load_local_supplier_acs
print("acs_files", __import__("os").listdir("/opt/agentlink/acs"))
print("local_n", len(load_local_supplier_acs()))
for c in load_local_supplier_acs():
    print(" L", c["agent_id"], c["name"][:20], c["aic"][-18:])
r = asyncio.run(discover_suppliers("采联供应商智能体 报价 议价 原料", limit=5))
print("source", r["source"])
print("err", r.get("platform_error"))
print("url", r.get("discovery_url"))
for c in r["candidates"]:
    print(" C", c["agent_id"], c["source"], c["name"][:24], (c.get("endpoint") or "")[:50])
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
    sftp = c.open_sftp()
    with sftp.file("/tmp/dbg_disc.py", "w") as f:
        f.write(REMOTE_PY)
    sftp.close()
    _, stdout, _ = c.exec_command(
        "systemctl restart agentlink-buyer-a; sleep 2; "
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python /tmp/dbg_disc.py",
        timeout=90,
        get_pty=True,
    )
    print(stdout.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
