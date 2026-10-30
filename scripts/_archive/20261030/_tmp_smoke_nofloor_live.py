
import json, ssl, urllib.request, uuid
from datetime import datetime, timezone
ctx = ssl._create_unverified_context()

def now():
    return datetime.now(timezone.utc).isoformat()

def rpc(port, schema, payload):
    tid = "live-" + uuid.uuid4().hex[:8]
    envelope = {
        "schema_type": schema,
        "schema_version": "1.0",
        "business_id": "biz-" + tid,
        "payload": payload,
    }
    body = {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": tid,
        "params": {
            "command": {
                "type": "task-command",
                "id": "cmd-" + tid,
                "sentAt": now(),
                "senderRole": "leader",
                "senderId": "buyer-a-local-aic",
                "sessionId": "sess-" + tid,
                "taskId": tid,
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
    "purchase_request_id": "pr-live",
    "quantity": 100,
    "product_name": "RM-CASTER-300",
    "sku": "RM-CASTER-300",
    "specifications": {"sku": "RM-CASTER-300"},
    "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
    "need_freight": False,
}
q = rpc(8011, "agentlink.quote_request", base)
q5 = rpc(8011, "agentlink.quote_request", dict(base, quantity=500, purchase_request_id="pr-live-500"))
b = rpc(8011, "agentlink.bargain_round", dict(base, previous_unit_price=20, goal_text="优化综合成本"))
qb = rpc(8013, "agentlink.quote_request", {
    "purchase_request_id": "pr-b",
    "quantity": 200,
    "product_name": "RM-FABRIC-PRO",
    "sku": "RM-FABRIC-PRO",
    "specifications": {"sku": "RM-FABRIC-PRO", "material": "steel", "color": "black"},
    "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
    "need_freight": False,
})
qc = rpc(8014, "agentlink.quote_request", {
    "purchase_request_id": "pr-c",
    "quantity": 50,
    "product_name": "RM-TUBE-STEEL",
    "sku": "RM-TUBE-STEEL",
    "specifications": {"sku": "RM-TUBE-STEEL"},
    "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
    "need_freight": False,
})
print("A100", q.get("unit_price"), q.get("pricing_mode"), q.get("runtime"))
print("A500", q5.get("unit_price"), q5.get("bargain_room"), q5.get("pricing_mode"))
print("A_bargain", b.get("unit_price"), b.get("pricing_mode"))
print("B200", qb.get("unit_price"), qb.get("pricing_mode"), qb.get("runtime"))
print("C50", qc.get("unit_price"), qc.get("pricing_mode"), qc.get("runtime"))
ok = (
    float(q.get("unit_price") or -1) == 20.0
    and float(q5.get("unit_price") or -1) == 18.0
    and float(b.get("unit_price") or -1) == 20.0
    and float(qb.get("unit_price") or -1) == 35.0
    and float(qc.get("unit_price") or -1) == 100.0
    and q.get("pricing_mode") == "list_plus_promo_only"
)
print("LIVE_PASS" if ok else "LIVE_FAIL")
