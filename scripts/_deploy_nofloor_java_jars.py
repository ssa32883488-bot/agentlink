# -*- coding: utf-8 -*-
"""Upload rebuilt Java supplier jars, restart, smoke quote/bargain no-floor."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
JAR_MAP = {
    "java-suppliers/supplier-a/build/libs/supplier-a-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-a.jar",
    "java-suppliers/supplier-b/build/libs/supplier-b-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-b.jar",
    "java-suppliers/supplier-c/build/libs/supplier-c-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-c.jar",
}


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
    r = httpx.post(url, json=body, timeout=60.0, verify=False)
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
    for local in JAR_MAP:
        p = ROOT / local
        if not p.is_file():
            print("MISSING", local)
            return 2
        print("jar", local, p.stat().st_size, flush=True)

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    with SCPClient(c.get_transport()) as scp:
        for local, remote in JAR_MAP.items():
            scp.put(str(ROOT / local), remote)
            print("put", local, "->", remote, flush=True)
    _, o, e = c.exec_command(
        """
set -e
mkdir -p /opt/agentlink/java-suppliers
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
# cold start ~45s
sleep 50
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
curl -sk -m 10 https://127.0.0.1:8011/health; echo
curl -sk -m 10 https://127.0.0.1:8013/health; echo
curl -sk -m 10 https://127.0.0.1:8014/health; echo
curl -sf http://127.0.0.1:18011/api/erp/catalog | python3 -c 'import sys,json; d=json.load(sys.stdin); items=d.get("items") or [];
bad=[i for i in items if abs(float(i.get("floor_price",0))-float(i.get("list_price",0)))>1e-6];
print("catalog_rows",len(items),"floor_ne_list",len(bad))'
""",
        timeout=180,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", errors="replace"), flush=True)
    c.close()

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
    print("quoteA100", {k: q.get(k) for k in ("unit_price", "bargain_room", "pricing_mode", "runtime")}, flush=True)
    q500 = extract_payload(
        rpc(
            f"{base}:8011/rpc",
            "agentlink.quote_request",
            {**payload100, "quantity": 500, "purchase_request_id": "pr-nofloor-500"},
        )
    )
    print(
        "quoteA500",
        {k: q500.get(k) for k in ("unit_price", "bargain_room", "pricing_mode", "line_qty_discount")},
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
        {k: b.get(k) for k in ("unit_price", "bargain_room", "pricing_mode", "note")},
        flush=True,
    )

    ok = True
    if float(q.get("unit_price") or -1) != 20.0:
        print("FAIL unit@100", q.get("unit_price"))
        ok = False
    if float(q500.get("unit_price") or -1) != 18.0:
        print("FAIL unit@500 promo", q500.get("unit_price"))
        ok = False
    if float(b.get("unit_price") or -1) != 20.0:
        print("FAIL bargain cut list", b.get("unit_price"))
        ok = False
    if float(q500.get("bargain_room") or 0) <= 0:
        print("FAIL bargain_room@500", q500.get("bargain_room"))
        ok = False
    print("PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
