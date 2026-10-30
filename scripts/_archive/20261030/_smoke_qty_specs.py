# -*- coding: utf-8 -*-
"""Smoke: initial quote has physical specs; bargain+decide path notes."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import paramiko

PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE = r'''
set -e
sleep 8
/opt/agentlink/.venv/bin/python - <<'PY'
import json, uuid, urllib.request, ssl
from datetime import datetime, timezone

def rpc(schema, payload):
    tid = "smoke-" + uuid.uuid4().hex[:8]
    env = {"schema_type": schema, "schema_version": "1.0", "business_id": "biz-"+tid, "payload": payload}
    body = {"jsonrpc":"2.0","method":"rpc","id":tid,"params":{"command":{
        "type":"task-command","id":"cmd-"+tid,
        "sentAt": datetime.now(timezone.utc).isoformat(),
        "senderRole":"leader","senderId":"buyer-a",
        "sessionId":"sess-"+tid,"taskId":tid,"command":"start",
        "dataItems":[{"type":"data","data":env}],
    }}}
    req = urllib.request.Request(
        "https://127.0.0.1:8011/rpc", data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json"}, method="POST")
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        data = json.load(r)
    products = ((data.get("result") or {}).get("products") or [])
    items = (products[0].get("dataItems") or []) if products else []
    return ((items[0].get("data") or {}).get("payload")) or {} if items else {}

base = {
    "purchase_request_id": "pr-qty",
    "quantity": 300,
    "product_name": "重型脚轮",
    "sku": "RM-CASTER-300",
    "specifications": {"sku": "RM-CASTER-300"},
    "destination": {"province": "河北", "city": "保定"},
    "need_freight": False,
}
q = rpc("agentlink.quote_request", base)
prod = q.get("product") or {}
print("initial", {
    "unit": q.get("unit_price"),
    "vol": q.get("volume_m3") or prod.get("volume_m3"),
    "kg": q.get("weight_kg") or prod.get("weight_kg"),
    "pack": prod.get("pack_cm"),
    "promo": q.get("promotions_disclosed"),
})
ok = True
if not (q.get("volume_m3") or prod.get("volume_m3")):
    print("FAIL no volume"); ok=False
if not (q.get("weight_kg") or prod.get("weight_kg")):
    print("FAIL no weight"); ok=False
if q.get("promotions_disclosed") is not False:
    print("FAIL promo leaked"); ok=False
# local settle sanity for 500
import sys
sys.path.insert(0,"/opt/agentlink")
from commerce.flow_service import _settle_order_price
u,g,e = _settle_order_price(supplier_agent_id="supplier-a", sku="RM-CASTER-300", qty=500, list_unit=20)
print("settle500", u, g)
if abs(float(u)-18)>1e-6 or abs(float(g)-9000)>1e-6:
    print("FAIL settle"); ok=False
print("PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
PY
'''


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    # also push flow_service settle helper used in smoke — already on buyer; settle uses code on aliyun?
    # settle is imported from /opt/agentlink on aliyun — need flow_service there too for smoke
    sftp = c.open_sftp()
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sftp.put(str(root / "commerce/flow_service.py"), "/opt/agentlink/commerce/flow_service.py")
    sftp.close()
    _, o, e = c.exec_command(REMOTE, timeout=120, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", "replace")
    print(out, flush=True)
    c.close()
    return 0 if "PASS" in out and "FAIL" not in out.split("PASS")[0] else (0 if out.strip().endswith("PASS") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
