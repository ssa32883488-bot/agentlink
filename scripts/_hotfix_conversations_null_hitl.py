# -*- coding: utf-8 -*-
"""热修：conversations 在 hitl_pending=null 时 500，导致对话历史空白。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    print("$", cmd[:160], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out[-2000:], flush=True)
    return out


def main() -> None:
    c = connect()
    rel = "commerce_v2/routes.py"
    remote = f"/opt/agentlink/{rel}"
    with SCPClient(c.get_transport()) as scp:
        run(c, f"mkdir -p {Path(remote).parent.as_posix()}")
        print("put", rel, flush=True)
        scp.put(str(ROOT / rel), remote)
        run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")
    run(
        c,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 2; "
        "systemctl is-active agentlink-buyer-a agentlink-buyer-b",
    )
    run(
        c,
        "curl -sk -m 10 'https://127.0.0.1:8010/api/erp/conversations?limit=3' "
        "| python3 -c 'import sys,json; d=json.load(sys.stdin); "
        "print(\"ok items\",len(d.get(\"items\") or []),\"thread\",d.get(\"thread_id\"),"
        "\"case\",d.get(\"case_id\")); "
        "print((d.get(\"items\") or [{}])[-1].get(\"role\"),(d.get(\"items\") or [{}])[-1].get(\"content\",\"\")[:80])'",
    )
    run(
        c,
        "curl -sk -m 10 'https://127.0.0.1:8090/api/proxy/buyer-a/api/erp/conversations?limit=2' "
        "| python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"proxy items\",len(d.get(\"items\") or []), d.get(\"thread_id\"))'",
    )
    c.close()
    print("HOTFIX_CONVERSATIONS_NULL_HITL_DONE", flush=True)


if __name__ == "__main__":
    main()
