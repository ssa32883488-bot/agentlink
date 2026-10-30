# -*- coding: utf-8 -*-
"""Run quote/bargain smoke on Aliyun via localhost RPC (avoid WAN TLS flakiness)."""
from __future__ import annotations

import os

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE = r'''
set -e
sleep 15
systemctl is-active agentlink-supplier-a
/opt/agentlink/.venv/bin/python - <<'PY'
import json, uuid, urllib.request, ssl
from datetime import datetime, timezone

def rpc(schema, payload):
    tid = "smoke-" + uuid.uuid4().hex[:8]
    env = {"schema_type": schema, "schema_version": "1.0", "business_id": "biz-"+tid, "payload": payload}
    body = {
        "jsonrpc": "2.0", "method": "rpc", "id": tid,
        "params": {"command": {
            "type": "task-command", "id": "cmd-"+tid,
            "sentAt": datetime.now(timezone.utc).isoformat(),
            "senderRole": "leader", "senderId": "buyer-a",
            "sessionId": "sess-"+tid, "taskId": tid, "command": "start",
            "dataItems": [{"type": "data", "data": env}],
        }},
    }
    req = urllib.request.Request(
        "https://127.0.0.1:8011/rpc",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        data = json.load(r)
    products = ((data.get("result") or {}).get("products") or [])
    if not products:
        return {}
    items = products[0].get("dataItems") or []
    if not items:
        return {}
    return ((items[0].get("data") or {}).get("payload")) or {}

base = {
    "purchase_request_id": "pr-phase",
    "quantity": 300,
    "product_name": "重型脚轮",
    "sku": "RM-CASTER-300",
    "specifications": {"sku": "RM-CASTER-300"},
    "destination": {"province": "河北", "city": "保定", "postal_code": "071000"},
    "need_freight": False,
}
q = rpc("agentlink.quote_request", base)
print("initial", {k: q.get(k) for k in ("unit_price","pricing_mode","promotions_disclosed","policy_hints","note")})
q5 = rpc("agentlink.quote_request", {**base, "quantity": 500, "purchase_request_id": "pr-phase-500"})
print("initial500", {k: q5.get(k) for k in ("unit_price","pricing_mode","promotions_disclosed","policy_hints")})
b = rpc("agentlink.bargain_round", {**base, "previous_unit_price": 20, "goal_text": "请问有没有价格优惠？"})
pol = b.get("policy") if isinstance(b.get("policy"), dict) else {}
reach = pol.get("reach_example") or b.get("reach_promo_preview") or {}
print("bargain", {
    "unit_price": b.get("unit_price"),
    "promotions_disclosed": b.get("promotions_disclosed"),
    "hints": (pol.get("hints") or b.get("policy_hints") or [])[:1],
    "reach": reach,
    "talk": (b.get("talk_track") or "")[:80],
})
ok = True
if float(q.get("unit_price") or -1) != 20: print("FAIL unit"); ok=False
if q.get("promotions_disclosed") is not False: print("FAIL disclose"); ok=False
if q.get("policy_hints") not in (None, [], {}): print("FAIL leak", q.get("policy_hints")); ok=False
if float(q5.get("unit_price") or -1) != 20: print("FAIL unit500", q5.get("unit_price")); ok=False
if not (pol.get("hints") or b.get("policy_hints")): print("FAIL hints"); ok=False
if float((reach or {}).get("goods_after_promo") or 0) != 9000: print("FAIL reach", reach); ok=False
print("PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
PY
'''


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(REMOTE, timeout=180, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", "replace")
    print(out, flush=True)
    c.close()
    return 0 if "\nPASS" in out or out.strip().endswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
