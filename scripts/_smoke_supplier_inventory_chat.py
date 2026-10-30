# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

import paramiko

HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
REMOTE = r"""
set -e
curl -sS -m 25 -X POST http://127.0.0.1:18011/api/erp/chat \
  -H 'content-type: application/json' \
  -d '{"text":"查看库存"}' > /tmp/sup_chat.json
python3 - <<'PY'
import json
o=json.load(open('/tmp/sup_chat.json',encoding='utf-8'))
reply=o.get('reply') or ''
intent=o.get('intent') or (o.get('meta') or {}).get('intent')
# handle_supplier_chat returns intent inside meta merge: **meta so intent at top level
print('intent', o.get('intent'))
print('engine', o.get('engine'))
snip=reply.replace('\n',' | ')[:400]
print('reply', snip.encode('utf-8','replace').decode('utf-8'))
ok=('RM-' in reply) and ('挂牌' in reply or '可售' in reply) and not reply.startswith('我是供应商助手')
print('PASS' if ok else 'FAIL')
PY
curl -sS -m 25 -X POST http://127.0.0.1:8091/api/proxy/supplier-a/api/erp/chat \
  -H 'content-type: application/json' \
  -d '{"text":"价目"}' | python3 -c 'import sys,json; o=json.load(sys.stdin); r=o.get("reply") or ""; print("ui_proxy", "OK" if "RM-" in r else "BAD", o.get("intent"))'
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(REMOTE, timeout=60, get_pty=True)
    raw = o.read() + e.read()
    out = raw.decode("utf-8", errors="replace")
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace") + b"\n")
    sys.stdout.buffer.flush()
    c.close()
    return 0 if "PASS" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
