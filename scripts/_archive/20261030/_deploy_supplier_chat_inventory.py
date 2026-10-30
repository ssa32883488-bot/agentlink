# -*- coding: utf-8 -*-
"""Deploy chat_supplier inventory intents; restart ERP sidecars; smoke 查看库存."""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(ROOT / "commerce/chat_supplier.py"), "/opt/agentlink/commerce/chat_supplier.py")
        print("put chat_supplier.py", flush=True)
    _, o, e = c.exec_command(
        r"""
set -e
systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp
sleep 4
systemctl is-active agentlink-supplier-a-erp
# direct ERP sidecar (no java) chat
curl -sS -m 20 -X POST http://127.0.0.1:18011/api/erp/chat/stream \
  -H 'content-type: application/json' \
  -d '{"text":"查看库存","thread_id":null}' | tee /tmp/sup_chat.sse | head -c 1200
echo
# also via UI proxy
curl -sS -m 20 -X POST http://127.0.0.1:8091/api/proxy/supplier-a/api/erp/chat/stream \
  -H 'content-type: application/json' \
  -d '{"text":"查看库存"}' | head -c 800
echo
python3 - <<'PY'
import re
raw=open('/tmp/sup_chat.sse','r',encoding='utf-8',errors='replace').read()
# SSE may be data: {...}
texts=[]
for m in re.finditer(r'data:\s*(\{.*?\})(?:\n|$)', raw, re.S):
    try:
        import json
        o=json.loads(m.group(1))
        if o.get('type')=='done':
            texts.append(o.get('reply') or '')
        if o.get('type')=='token' and o.get('text'):
            pass
    except Exception:
        pass
# fallback: whole body json
if not texts:
    try:
        import json
        o=json.loads(raw)
        texts.append(o.get('reply') or '')
    except Exception:
        texts.append(raw)
reply=''.join(texts) or raw
print('REPLY_SNIP', reply[:300].replace('\n',' | '))
ok = ('挂牌' in reply or '可售' in reply or 'RM-' in reply) and '我是供应商助手' not in reply[:40]
print('PASS' if ok else 'FAIL')
PY
""",
        timeout=90,
        get_pty=True,
    )
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out, flush=True)
    c.close()
    return 0 if "\nPASS" in out or out.strip().endswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
