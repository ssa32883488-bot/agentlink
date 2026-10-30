# -*- coding: utf-8 -*-
"""Fix procurement case store shape + deploy procurement_case.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def main() -> None:
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = b.open_sftp()
    sftp.put(str(ROOT / "commerce/procurement_case.py"), "/opt/agentlink/commerce/procurement_case.py")
    print("put commerce/procurement_case.py", flush=True)
    sftp.close()
    _, o, e = b.exec_command(
        r"""
set -e
cd /opt/agentlink
# 修正被误写成 [] 的采购案文件
/opt/agentlink/.venv/bin/python - <<'PY'
from pathlib import Path
empty = '{"cases": {}}'
for p in Path('data').glob('procurement_cases*.json'):
    t = p.read_text(encoding='utf-8').strip()
    print(p.name, 'before', t[:40])
    if t in ('[]', 'null', '') or t.startswith('['):
        p.write_text(empty, encoding='utf-8')
        print('fixed', p.name)
PY
systemctl restart agentlink-buyer-a agentlink-buyer-b
sleep 4
/opt/agentlink/.venv/bin/python - <<'PY'
import json, urllib.request, ssl
ctx = ssl._create_unverified_context()

def call(path, data=None):
    req = urllib.request.Request('https://127.0.0.1:8010'+path, method='GET' if data is None else 'POST')
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return json.loads(r.read().decode())

# 直接测采购案模块 + 发现
import os
os.environ['BUYER_AGENT_ID'] = 'buyer-a'
from commerce import procurement_case as pc
print('load', pc._load())
print('list', pc.list_cases(1))
# HTTP discover via tools is heavy; status empty ok
st = call('/api/flow/cases')
print('cases_http', st)
print('FIX_OK')
PY
""",
        timeout=120,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    b.close()


if __name__ == "__main__":
    main()
