# -*- coding: utf-8 -*-
"""Deploy no-floor / promo-only pricing to Aliyun; reseed; smoke quote+bargain."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

PY_FILES = [
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

JAR_MAP = {
    "java-suppliers/supplier-a/build/libs/supplier-a-0.1.0.jar": "/opt/agentlink/java/supplier-a.jar",
    "java-suppliers/supplier-b/build/libs/supplier-b-0.1.0.jar": "/opt/agentlink/java/supplier-b.jar",
    "java-suppliers/supplier-c/build/libs/supplier-c-0.1.0.jar": "/opt/agentlink/java/supplier-c.jar",
}


def run_local(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(cwd or ROOT))


def ssh_run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    data = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(data, flush=True)
    return data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rpc(url: str, schema: str, payload: dict) -> dict:
    task_id = f"smoke-{uuid.uuid4().hex[:8]}"
    envelope = {
        "schema_type": schema,
        "schema_version": "1.0",
        "business_id": f"biz-{task_id}",
        "payload": payload,
    }
    body = {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": task_id,
        "params": {
            "command": {
                "type": "task-command",
                "id": f"cmd-{task_id}",
                "sentAt": _now(),
                "senderRole": "leader",
                "senderId": "buyer-a-local-aic",
                "sessionId": f"sess-{task_id}",
                "taskId": task_id,
                "command": "start",
                "dataItems": [{"type": "data", "data": envelope}],
            }
        },
    }
    r = httpx.post(url, json=body, timeout=45.0, verify=False)
    r.raise_for_status()
    return r.json()


def extract_payload(data: dict) -> dict:
    result = data.get("result") or {}
    products = result.get("products") or []
    if not products:
        return {}
    items = products[0].get("dataItems") or []
    if not items:
        return {}
    env = items[0].get("data") or {}
    return env.get("payload") or {}


def main() -> int:
    run_local(
        [
            sys.executable,
            "-c",
            (
                "from agents.supplier_common.promo import goodwill_unit_price, promo_leverage_amount, settle_quote_economics;"
                "from agents.supplier_common.catalog_price import quote_from_catalog;"
                "import yaml; from pathlib import Path;"
                "p=yaml.safe_load(Path('agents/supplier_a/policy.yaml').read_text(encoding='utf-8'));"
                "q=quote_from_catalog(p,100,sku='RM-CASTER-300');"
                "assert q['floor_price']==q['unit_price']==20.0;"
                "assert goodwill_unit_price(p,previous_unit=20,quantity=100)==20.0;"
                "e=settle_quote_economics(p,qty=500,unit_price=20,sku='RM-CASTER-300');"
                "assert e['line_qty_save']>0;"
                "assert promo_leverage_amount(e)>=e['line_qty_save'];"
                "print('local_py_ok', e['line_qty_save'], promo_leverage_amount(e))"
            ),
        ]
    )

    gradlew = ROOT / "java-suppliers" / ("gradlew.bat" if os.name == "nt" else "gradlew")
    run_local(
        [str(gradlew), ":supplier-a:bootJar", ":supplier-b:bootJar", ":supplier-c:bootJar", "-q"],
        ROOT / "java-suppliers",
    )

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    with SCPClient(c.get_transport()) as scp:
        for rel in PY_FILES:
            remote = f"/opt/agentlink/{rel}"
            parent = remote.rsplit("/", 1)[0]
            ssh_run(c, f"mkdir -p {parent}", timeout=20)
            scp.put(str(ROOT / rel), remote)
            print("put", rel, flush=True)
        for local, remote in JAR_MAP.items():
            scp.put(str(ROOT / local), remote)
            print("put", local, "->", remote, flush=True)

    ssh_run(
        c,
        r"""
set -e
cd /opt/agentlink
.venv/bin/python -m commerce.seed
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c \
  agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp \
  agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c || true
sleep 35
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
curl -sk -m 10 https://127.0.0.1:8011/health; echo
curl -sf http://127.0.0.1:18011/api/erp/catalog | python3 -c 'import sys,json; d=json.load(sys.stdin); items=d.get("items") or [];
bad=[i for i in items if abs(float(i.get("floor_price",0))-float(i.get("list_price",0)))>1e-6];
print("catalog_rows",len(items),"floor_ne_list",len(bad));
print([(i["code"],i["list_price"],i.get("floor_price")) for i in items[:4]])'
""",
        timeout=240,
    )
    c.close()

    # remote public AIP smoke from local machine
    base = f"https://{HOST}"
    payload100 = {
        "purchase_request_id": "pr-nofloor",
        "quantity": 100,
        "product_name": "RM-CASTER-300",
        "sku": "RM-CASTER-300",
        "specifications": {"sku": "RM-CASTER-300"},
        "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
        "need_freight": False,
    }
    q = extract_payload(rpc(f"{base}:8011/rpc", "agentlink.quote_request", payload100))
    print("quoteA100", {k: q.get(k) for k in ("unit_price", "bargain_room", "pricing_mode", "runtime", "floor_price")}, flush=True)
    q500 = extract_payload(
        rpc(
            f"{base}:8011/rpc",
            "agentlink.quote_request",
            {**payload100, "quantity": 500, "purchase_request_id": "pr-nofloor-500"},
        )
    )
    print(
        "quoteA500",
        {
            k: q500.get(k)
            for k in ("unit_price", "bargain_room", "pricing_mode", "line_qty_discount")
        },
        flush=True,
    )
    b = extract_payload(
        rpc(
            f"{base}:8011/rpc",
            "agentlink.bargain_round",
            {**payload100, "previous_unit_price": 20, "goal_text": "优化综合成本"},
        )
    )
    print(
        "bargainA",
        {
            k: b.get(k)
            for k in ("unit_price", "bargain_room", "pricing_mode", "note", "negotiation_style")
        },
        flush=True,
    )

    ok = True
    if float(q.get("unit_price") or 0) != 20.0:
        print("FAIL unit@100 should stay list 20", q.get("unit_price"))
        ok = False
    if float(q500.get("unit_price") or 0) != 18.0:
        print("FAIL unit@500 should be promo 18", q500.get("unit_price"))
        ok = False
    if float(b.get("unit_price") or 0) != 20.0:
        print("FAIL bargain must not cut list unit", b.get("unit_price"))
        ok = False
    if q.get("pricing_mode") != "list_plus_promo_only" and b.get("pricing_mode") != "list_plus_promo_only":
        print("WARN missing pricing_mode flag")
    if float(q500.get("bargain_room") or 0) <= 0:
        print("FAIL bargain_room@500 should reflect promo leverage", q500.get("bargain_room"))
        ok = False

    print("PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
