# -*- coding: utf-8 -*-
"""P0 RPC 路径冒烟：在采购机上调 /api/erp/group/open → 远程 /group/join → ping → dissolve。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"

REMOTE = r"""
set -e
cd /opt/agentlink
/opt/agentlink/.venv/bin/python - <<'PY'
import json, os, urllib.request, ssl
os.chdir('/opt/agentlink')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def post(url, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={'content-type':'application/json'}, method='POST')
    with urllib.request.urlopen(req, context=ctx, timeout=120) as r:
        return json.loads(r.read().decode())

base = os.environ.get('BUYER_A_LOCAL', 'https://127.0.0.1:8010')
print('open...', flush=True)
opened = post(base + '/api/erp/group/open', {
    'members': ['supplier-a','supplier-b','supplier-c','logistics'],
    'invite': True,
})
print('OPEN', json.dumps(opened, ensure_ascii=False), flush=True)
sid = opened.get('session_id')
members = opened.get('members') or []
joined = [m for m in members if m.get('status')=='joined']
print('joined_count', len(joined), flush=True)
if not sid or len(joined) < 4:
    raise SystemExit(1)
print('ping...', flush=True)
ping = post(base + f'/api/erp/group/{sid}/ping')
print('PING', json.dumps(ping, ensure_ascii=False), flush=True)
got = set(ping.get('got') or [])
expected = set(ping.get('expected') or [])
ok = bool(expected) and expected.issubset(got)
post(base + f'/api/erp/group/{sid}/dissolve')
print('PASS' if ok else 'FAIL', 'got', sorted(got), flush=True)
raise SystemExit(0 if ok else 1)
PY
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    # upload smoke helper already inlined; ensure env RPC urls
    _, o, e = c.exec_command(
        r"""
cd /opt/agentlink
grep -q '^SUPPLIER_A_RPC_URL=' .env || echo 'SUPPLIER_A_RPC_URL=https://39.105.20.113:8011/rpc' >> .env
grep -q '^SUPPLIER_B_RPC_URL=' .env || echo 'SUPPLIER_B_RPC_URL=https://39.105.20.113:8013/rpc' >> .env
grep -q '^SUPPLIER_C_RPC_URL=' .env || echo 'SUPPLIER_C_RPC_URL=https://39.105.20.113:8014/rpc' >> .env
grep -q '^LOGISTICS_RPC_URL=' .env || echo 'LOGISTICS_RPC_URL=https://ashui.online:8015/rpc' >> .env
grep -E 'RPC_URL|ACPS_MQ_' .env | head -30
""",
        timeout=60,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    _, o, e = c.exec_command(REMOTE, timeout=300, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    code = o.channel.recv_exit_status()
    c.close()
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
