# -*- coding: utf-8 -*-
"""冒烟：向 Java 供应 A/B/C 的 /rpc 发 quote_request，校验 initial_quote。"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TARGETS = (
    ("supplier-a", "http://127.0.0.1:8011/rpc", "RM-CASTER-300", 500),
    ("supplier-b", "http://127.0.0.1:8013/rpc", "RM-FABRIC-PRO", 100),
    ("supplier-c", "http://127.0.0.1:8014/rpc", "RM-TUBE-STEEL", 50),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rpc_quote(url: str, *, sku: str, qty: int, agent: str) -> dict:
    task_id = f"smoke-{uuid.uuid4().hex[:8]}"
    envelope = {
        "schema_type": "agentlink.quote_request",
        "schema_version": "1.0",
        "business_id": f"biz-{task_id}",
        "payload": {
            "purchase_request_id": f"pr-{task_id}",
            "quantity": qty,
            "product_name": sku,
            "sku": sku,
            "specifications": {"sku": sku, "material": "demo", "color": "black"},
            "dest_province": "河北",
            "destination": {"province": "河北", "postal_code": "071000", "city": "保定"},
            "need_freight": False,
        },
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
    r = httpx.post(url, json=body, timeout=30.0)
    r.raise_for_status()
    return r.json()


def main() -> int:
    ok = True
    for agent, url, sku, qty in TARGETS:
        try:
            h = httpx.get(url.replace("/rpc", "/health"), timeout=5.0)
            health = h.json()
            if health.get("runtime") != "java":
                print("WARN", agent, "health runtime != java", health)
            data = rpc_quote(url, sku=sku, qty=qty, agent=agent)
            result = data.get("result") or {}
            state = (result.get("status") or {}).get("state")
            products = result.get("products") or []
            env = None
            if products:
                items = products[0].get("dataItems") or []
                if items:
                    env = items[0].get("data")
            unit = (env or {}).get("payload", {}).get("unit_price") if env else None
            runtime = (env or {}).get("payload", {}).get("runtime") if env else None
            print(
                "OK" if state == "awaiting-completion" and unit is not None else "FAIL",
                agent,
                "state",
                state,
                "unit",
                unit,
                "runtime",
                runtime,
                flush=True,
            )
            if state != "awaiting-completion" or unit is None:
                ok = False
                print(json.dumps(data, ensure_ascii=False)[:800])
            if agent == "supplier-a" and qty >= 500 and unit is not None and abs(float(unit) - 18.0) > 0.01:
                print("FAIL caster 500 should be 18, got", unit)
                ok = False
        except Exception as exc:  # noqa: BLE001
            ok = False
            print("FAIL", agent, exc, flush=True)
    print("PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
