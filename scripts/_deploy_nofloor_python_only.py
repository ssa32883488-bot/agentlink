# -*- coding: utf-8 -*-
"""Deploy Python/policy/seed/UI no-floor changes while Java jars rebuild."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
HOSTS = [
    ("aliyun", "39.105.20.113", os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"), True),
]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER_HOST = "81.70.46.119"

FILES = [
    "agents/supplier_a/policy.yaml",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_c/policy.yaml",
    "agents/supplier_common/promo.py",
    "agents/supplier_common/negotiate.py",
    "agents/supplier_common/catalog_price.py",
    "commerce/seat_catalog.py",
    "commerce/seed.py",
    "commerce/scheme_planner.py",
    "ui/static/app.js",
    "docs/six_agents_tech_stack_and_params.md",
]


def connect(host: str, password: str | None = None) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        c.connect(host, username="root", password=password, timeout=40, allow_agent=False, look_for_keys=False)
    else:
        c.connect(host, username="root", pkey=paramiko.RSAKey.from_private_key_file(str(PEM)), timeout=40, allow_agent=False, look_for_keys=False)
    return c


def put_all(c: paramiko.SSHClient) -> None:
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            parent = remote.rsplit("/", 1)[0]
            _, o, _ = c.exec_command(f"mkdir -p {parent}")
            o.channel.recv_exit_status()
            scp.put(str(ROOT / rel), remote)
            print("put", rel, flush=True)


def main() -> int:
    # Aliyun: seed + UI + erp restart (Java jars later)
    c = connect("39.105.20.113", os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"))
    put_all(c)
    _, o, e = c.exec_command(
        """
cd /opt/agentlink && .venv/bin/python -m commerce.seed
systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp \
  agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c || true
sleep 3
curl -sf http://127.0.0.1:18011/api/erp/catalog | python3 -c 'import sys,json; d=json.load(sys.stdin); items=d.get("items") or [];
bad=[i for i in items if abs(float(i.get("floor_price",0))-float(i.get("list_price",0)))>1e-6];
print("aliyun_catalog",len(items),"floor_ne_list",len(bad))'
""",
        timeout=90,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", errors="replace"), flush=True)
    c.close()

    # Tencent buyer/logistics: scheme_planner + supplier policies for buyer promo leverage
    try:
        c2 = connect(BUYER_HOST)
        put_all(c2)
        _, o2, e2 = c2.exec_command(
            """
cd /opt/agentlink && .venv/bin/python -m commerce.seed || true
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics || true
sleep 2
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics || true
""",
            timeout=90,
            get_pty=True,
        )
        print((o2.read() + e2.read()).decode("utf-8", errors="replace"), flush=True)
        c2.close()
    except Exception as exc:  # noqa: BLE001
        print("WARN buyer deploy:", exc, flush=True)
    print("python_side_deployed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
