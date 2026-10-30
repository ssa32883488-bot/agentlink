# -*- coding: utf-8 -*-
"""热修：物流工单 id 误用 order_id → ack-logistics 404。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
REL = "commerce_v2/order_ids.py"


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    print("$", cmd[:140], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=90, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out[-1600:], flush=True)
    return out


def put(c: paramiko.SSHClient) -> None:
    remote = f"/opt/agentlink/{REL}"
    with SCPClient(c.get_transport()) as scp:
        run(c, f"mkdir -p {Path(remote).parent.as_posix()}")
        print("put", REL, flush=True)
        scp.put(str(ROOT / REL), remote)
        run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{REL} 2>/dev/null || true")


def main() -> None:
    cb = connect("buyer")
    put(cb)
    run(
        cb,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; sleep 2; "
        "systemctl is-active agentlink-buyer-a agentlink-logistics",
    )
    run(
        cb,
        "curl -sk 'https://127.0.0.1:8010/api/erp/tickets' | python3 -c '"
        "import sys,json; "
        "items=json.load(sys.stdin).get(\"items\") or []; "
        "xs=[t for t in items if t.get(\"kind\")==\"logistics_order\"]; "
        "print([(t.get(\"id\"), t.get(\"order_id\"), t.get(\"logistics_id\"), t.get(\"title\",\"\")[:20]) for t in xs])'",
    )
    run(
        cb,
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "from commerce_v2 import order_ids\n"
        "from commerce_v2.gates import ack_logistics_gate\n"
        "items=order_ids.list_open_tickets('buyer-a')\n"
        "xs=[t for t in items if t.get('kind')=='logistics_order' and t.get('status')=='open']\n"
        "print('open logistics tickets', [(t['id'], t.get('order_id')) for t in xs])\n"
        "assert xs and str(xs[0]['id']).startswith('log-'), xs\n"
        "lid=xs[0]['id']\n"
        "# dry: lookup only\n"
        "row=order_ids._load()['logistics'].get(lid)\n"
        "print('lookup_ok', bool(row), 'buyer_ack', (row or {}).get('buyer_ack'))\n"
        "PY",
    )
    cb.close()

    cs = connect("supplier")
    put(cs)
    run(cs, "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 2; systemctl is-active agentlink-supplier-b")
    cs.close()
    print("HOTFIX_LOGISTICS_TICKET_ID_DONE", flush=True)


if __name__ == "__main__":
    main()
