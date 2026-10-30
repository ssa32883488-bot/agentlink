# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
FILES = [
    "commerce/chat_supplier_wit.py",
    "commerce/supplier_routes.py",
    "agents/supplier_a/policy.yaml",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_c/policy.yaml",
]


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            _, o, _ = c.exec_command(f"mkdir -p {remote.rsplit('/',1)[0]}")
            o.channel.recv_exit_status()
            scp.put(str(ROOT / rel), remote)
            print("put", rel, flush=True)
    _, o, e = c.exec_command(
        r"""
set -e
systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp
sleep 4
for port in 18011 18013 18014; do
  echo "== $port =="
  curl -sf http://127.0.0.1:$port/api/erp/promotions | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("agent_id"), "has", d.get("has_promotions"), d.get("summaries"))'
done
python3 - <<'PY'
import json, urllib.request
req=urllib.request.Request(
  'http://127.0.0.1:18011/api/erp/chat',
  data=json.dumps({"text":"你们有什么优惠政策？"}).encode(),
  headers={'content-type':'application/json'},
  method='POST',
)
with urllib.request.urlopen(req, timeout=120) as r:
  o=json.loads(r.read().decode())
reply=o.get('reply') or ''
print('engine', o.get('engine'), 'intent', o.get('intent'))
print('reply_snip', reply[:220].replace('\n',' | '))
ok = ('九折' in reply or '满' in reply or '脚轮' in reply or '折扣' in reply or '优惠' in reply) and '没有优惠字段' not in reply and '无可报价' not in reply
print('CHAT_PROMO_PASS' if ok else 'CHAT_PROMO_FAIL')
PY
""",
        timeout=200,
        get_pty=True,
    )
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    sys.stdout.buffer.write((out + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    c.close()
    return 0 if "CHAT_PROMO_PASS" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
