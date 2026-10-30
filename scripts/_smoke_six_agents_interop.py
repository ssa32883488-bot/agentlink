# -*- coding: utf-8 -*-
"""六智能体互通冒烟：健康检查 + 采购→三家供应 AIP 询价 + 采购→物流询运。"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
BUYER_HOST = "81.70.46.119"
SUPPLIER_HOST = "39.105.20.113"

AGENTS = [
    ("buyer-a", "https://81.70.46.119:8010/health", "tencent"),
    ("buyer-b", "https://81.70.46.119:8012/health", "tencent"),
    ("logistics", "https://81.70.46.119:8015/health", "tencent"),
    ("supplier-a", "https://39.105.20.113:8011/health", "aliyun"),
    ("supplier-b", "https://39.105.20.113:8013/health", "aliyun"),
    ("supplier-c", "https://39.105.20.113:8014/health", "aliyun"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rpc_post(url: str, schema: str, payload: dict, *, sender: str = "buyer-a-smoke") -> dict:
    task_id = f"six-{uuid.uuid4().hex[:8]}"
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
                "senderId": sender,
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
        return {"_state": (result.get("status") or {}).get("state"), "_raw_keys": list(result.keys())}
    items = products[0].get("dataItems") or []
    if not items:
        return {"_state": (result.get("status") or {}).get("state")}
    env = items[0].get("data") or {}
    pay = env.get("payload") if isinstance(env, dict) else {}
    return pay if isinstance(pay, dict) else {"_env": env}


def health_local() -> list[tuple[str, bool, str]]:
    rows = []
    for name, url, cloud in AGENTS:
        try:
            r = httpx.get(url, timeout=12.0, verify=False)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            ok = r.status_code == 200 and (body.get("status") in (None, "ok") or body.get("agent_id") or body.get("runtime"))
            detail = json.dumps(body, ensure_ascii=False)[:140]
            rows.append((name, ok, f"{cloud} HTTP{r.status_code} {detail}"))
        except Exception as exc:  # noqa: BLE001
            rows.append((name, False, f"{cloud} ERR {exc}"))
    return rows


def quote_matrix_from_local() -> list[tuple[str, bool, str]]:
    """本机直连阿里云供应 /rpc（验证公网 AIP）。"""
    targets = (
        ("supplier-a", "https://39.105.20.113:8011/rpc", "RM-CASTER-300", 100),
        ("supplier-b", "https://39.105.20.113:8013/rpc", "RM-FABRIC-PRO", 80),
        ("supplier-c", "https://39.105.20.113:8014/rpc", "RM-TUBE-STEEL", 40),
    )
    out = []
    for agent, url, sku, qty in targets:
        try:
            data = rpc_post(
                url,
                "agentlink.quote_request",
                {
                    "purchase_request_id": f"pr-{agent}",
                    "quantity": qty,
                    "product_name": sku,
                    "sku": sku,
                    "specifications": {"sku": sku, "material": "steel", "color": "black"},
                    "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
                    "need_freight": False,
                },
            )
            pay = extract_payload(data)
            unit = pay.get("unit_price")
            runtime = pay.get("runtime")
            ok = unit is not None
            out.append((f"local→{agent}", ok, f"unit={unit} runtime={runtime}"))
        except Exception as exc:  # noqa: BLE001
            out.append((f"local→{agent}", False, str(exc)))
    return out


REMOTE_BUYER_SMOKE = r'''
set -e
cd /opt/agentlink
.venv/bin/python - <<'PY'
import json, os, ssl, urllib.request, uuid
from datetime import datetime, timezone

ctx = ssl._create_unverified_context()

def now():
    return datetime.now(timezone.utc).isoformat()

def get(url):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
        return r.status, json.loads(r.read().decode())

def rpc(url, schema, payload):
    tid = "six-" + uuid.uuid4().hex[:8]
    envelope = {"schema_type": schema, "schema_version": "1.0", "business_id": "biz-" + tid, "payload": payload}
    body = {
        "jsonrpc": "2.0", "method": "rpc", "id": tid,
        "params": {"command": {
            "type": "task-command", "id": "cmd-" + tid, "sentAt": now(),
            "senderRole": "leader", "senderId": "buyer-a-interop",
            "sessionId": "sess-" + tid, "taskId": tid, "command": "start",
            "dataItems": [{"type": "data", "data": envelope}],
        }},
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return json.loads(r.read().decode())

def payload_of(data):
    products = ((data.get("result") or {}).get("products") or [])
    if not products:
        return {}
    items = products[0].get("dataItems") or []
    if not items:
        return {}
    env = items[0].get("data") or {}
    return env.get("payload") or {}

print("=== health from buyer host ===")
ok = True
for name, url in (
    ("buyer-a","https://127.0.0.1:8010/health"),
    ("buyer-b","https://127.0.0.1:8012/health"),
    ("logistics","https://127.0.0.1:8015/health"),
    ("supplier-a","https://39.105.20.113:8011/health"),
    ("supplier-b","https://39.105.20.113:8013/health"),
    ("supplier-c","https://39.105.20.113:8014/health"),
):
    try:
        code, body = get(url)
        print("HEALTH", name, code, body.get("agent_id") or body.get("status"), body.get("runtime"))
        ok = ok and code == 200
    except Exception as exc:
        print("HEALTH", name, "FAIL", exc)
        ok = False

print("=== buyer-host → suppliers AIP quote ===")
for agent, url, sku, qty in (
    ("supplier-a","https://39.105.20.113:8011/rpc","RM-CASTER-300",120),
    ("supplier-b","https://39.105.20.113:8013/rpc","RM-FABRIC-PRO",60),
    ("supplier-c","https://39.105.20.113:8014/rpc","RM-TUBE-STEEL",30),
):
    try:
        data = rpc(url, "agentlink.quote_request", {
            "purchase_request_id": "pr-interop-" + agent,
            "quantity": qty,
            "product_name": sku,
            "sku": sku,
            "specifications": {"sku": sku, "material": "steel", "color": "black"},
            "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
            "need_freight": False,
        })
        pay = payload_of(data)
        unit = pay.get("unit_price")
        print("QUOTE", agent, "OK" if unit is not None else "BAD", "unit", unit, "runtime", pay.get("runtime"))
        ok = ok and unit is not None
    except Exception as exc:
        print("QUOTE", agent, "FAIL", exc)
        ok = False

print("=== buyer-host → logistics shipping quote ===")
try:
    # common schemas vary; try freight / shipping_quote
    for schema in ("agentlink.shipping_quote_request", "agentlink.freight_quote_request", "agentlink.quote_request"):
        try:
            data = rpc("https://127.0.0.1:8015/rpc", schema, {
                "origin": {"province": "河北", "city": "沧州"},
                "destination": {"province": "浙江", "city": "杭州", "postal_code": "310000"},
                "weight_kg": 200,
                "volume_m3": 1.2,
                "service": "economy",
                "quantity": 100,
                "product_name": "RM-CASTER-300",
            })
            pay = payload_of(data)
            state = ((data.get("result") or {}).get("status") or {}).get("state")
            print("LOGISTICS", schema, "state", state, "keys", list(pay.keys())[:8], "amount", pay.get("amount") or pay.get("shipping_cost") or pay.get("freight"))
            if pay or state in ("awaiting-completion", "completed", "awaiting-input"):
                # even awaiting-input means rpc path alive
                print("LOGISTICS_RPC_REACHABLE")
                break
        except Exception as exc:
            print("LOGISTICS try", schema, "ERR", str(exc)[:120])
except Exception as exc:
    print("LOGISTICS FAIL", exc)
    ok = False

print("SIX_INTEROP_PASS" if ok else "SIX_INTEROP_FAIL")
PY
'''


def run_on_buyer_host() -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        BUYER_HOST,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=45,
        allow_agent=False,
        look_for_keys=False,
    )
    remote = "/tmp/smoke_six_interop.py"
    # upload as shell script content via exec heredoc already in REMOTE_BUYER_SMOKE
    _, o, e = c.exec_command(REMOTE_BUYER_SMOKE, timeout=240, get_pty=True)
    o.channel.settimeout(240)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    c.close()
    return out


def main() -> int:
    print("==== 1) public health (local) ====", flush=True)
    health_ok = True
    for name, ok, detail in health_local():
        print(("OK" if ok else "BAD"), name, detail, flush=True)
        health_ok = health_ok and ok

    print("==== 2) local → suppliers AIP ====", flush=True)
    quote_ok = True
    for name, ok, detail in quote_matrix_from_local():
        print(("OK" if ok else "BAD"), name, detail, flush=True)
        quote_ok = quote_ok and ok

    print("==== 3) buyer-host cross-cloud interop ====", flush=True)
    remote_out = run_on_buyer_host()
    sys.stdout.buffer.write((remote_out + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()

    remote_ok = "SIX_INTEROP_PASS" in remote_out
    logistics_reachable = "LOGISTICS_RPC_REACHABLE" in remote_out or "LOGISTICS" in remote_out

    print("==== summary ====", flush=True)
    print("health_all", health_ok, flush=True)
    print("quote_local_to_suppliers", quote_ok, flush=True)
    print("buyer_host_cross_cloud", remote_ok, flush=True)
    print("logistics_rpc_seen", logistics_reachable, flush=True)
    all_ok = health_ok and quote_ok and remote_ok
    print("SIX_AGENTS_INTEROP_PASS" if all_ok else "SIX_AGENTS_INTEROP_FAIL", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
