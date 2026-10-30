# -*- coding: utf-8 -*-
"""SSH onto Aliyun and smoke Java quote/bargain for no-floor promo-only."""
from __future__ import annotations

import os
import textwrap

import paramiko

HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE = textwrap.dedent(
    r"""
set -e
# wait until health responds
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sk -m 5 https://127.0.0.1:8011/health | grep -q java; then
    echo health_ok_$i
    break
  fi
  echo wait_$i
  sleep 5
done
curl -sk -m 8 https://127.0.0.1:8011/health; echo
curl -sf http://127.0.0.1:18011/api/erp/catalog | python3 -c 'import sys,json; d=json.load(sys.stdin); items=d.get("items") or [];
bad=[i for i in items if abs(float(i.get("floor_price",0))-float(i.get("list_price",0)))>1e-6];
print("catalog_rows",len(items),"floor_ne_list",len(bad))'
python3 - <<'PY'
import json, ssl, urllib.request, uuid
from datetime import datetime, timezone

ctx = ssl._create_unverified_context()

def now():
    return datetime.now(timezone.utc).isoformat()

def rpc(port, schema, payload):
    task_id = "smoke-" + uuid.uuid4().hex[:8]
    envelope = {
        "schema_type": schema,
        "schema_version": "1.0",
        "business_id": "biz-" + task_id,
        "payload": payload,
    }
    body = {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": task_id,
        "params": {
            "command": {
                "type": "task-command",
                "id": "cmd-" + task_id,
                "sentAt": now(),
                "senderRole": "leader",
                "senderId": "buyer-a-local-aic",
                "sessionId": "sess-" + task_id,
                "taskId": task_id,
                "command": "start",
                "dataItems": [{"type": "data", "data": envelope}],
            }
        },
    }
    req = urllib.request.Request(
        "https://127.0.0.1:%d/rpc" % port,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        data = json.loads(r.read().decode())
    products = ((data.get("result") or {}).get("products") or [])
    if not products:
        return {}
    items = products[0].get("dataItems") or []
    if not items:
        return {}
    return (items[0].get("data") or {}).get("payload") or {}

base = {
  "purchase_request_id": "pr-nofloor",
  "quantity": 100,
  "product_name": "RM-CASTER-300",
  "sku": "RM-CASTER-300",
  "specifications": {"sku": "RM-CASTER-300"},
  "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
  "need_freight": False,
}
q = rpc(8011, "agentlink.quote_request", base)
q500 = rpc(8011, "agentlink.quote_request", dict(base, quantity=500, purchase_request_id="pr-500"))
b = rpc(8011, "agentlink.bargain_round", dict(base, previous_unit_price=20, goal_text="优化综合成本"))
print("quoteA100", q.get("unit_price"), q.get("bargain_room"), q.get("pricing_mode"), q.get("runtime"))
print("quoteA500", q500.get("unit_price"), q500.get("bargain_room"), q500.get("pricing_mode"))
print("bargainA", b.get("unit_price"), b.get("bargain_room"), b.get("pricing_mode"), (b.get("note") or "")[:40])
ok = True
if float(q.get("unit_price") or -1) != 20.0:
    print("FAIL unit@100", q.get("unit_price")); ok=False
if float(q500.get("unit_price") or -1) != 18.0:
    print("FAIL unit@500", q500.get("unit_price")); ok=False
if float(b.get("unit_price") or -1) != 20.0:
    print("FAIL bargain cut", b.get("unit_price")); ok=False
if float(q500.get("bargain_room") or 0) <= 0:
    print("FAIL room@500", q500.get("bargain_room")); ok=False
print("PASS" if ok else "FAIL")
PY
"""
)


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    # ensure restarted with new jars
    _, o0, e0 = c.exec_command(
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 2; systemctl is-active agentlink-supplier-a",
        timeout=40,
        get_pty=True,
    )
    print((o0.read() + e0.read()).decode("utf-8", errors="replace"), flush=True)
    _, o, e = c.exec_command(REMOTE, timeout=180, get_pty=True)
    o.channel.settimeout(180)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out, flush=True)
    c.close()
    if "\nPASS" in out or out.strip().endswith("PASS"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
