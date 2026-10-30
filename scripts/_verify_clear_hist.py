# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

CMD = r"""
cd /opt/agentlink
echo '== data =='
ls -la data/ 2>/dev/null | head -40
echo '== sqlite counts =='
/opt/agentlink/.venv/bin/python - <<'PY'
import sqlite3, glob
paths = glob.glob('/opt/agentlink/data/*.sqlite3')
paths += glob.glob('/var/lib/agentlink/**/*.sqlite3', recursive=True)
paths += glob.glob('/opt/agentlink/**/data/*.sqlite3', recursive=True)
seen=set()
for db in paths:
    if db in seen: continue
    seen.add(db)
    try:
        con=sqlite3.connect(db)
        t={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts={}
        for x in ('work_tickets','conversations','chat_threads','inventory','materials','catalog'):
            if x in t:
                counts[x]=con.execute(f'SELECT COUNT(*) FROM {x}').fetchone()[0]
        print(db, counts or list(t)[:8])
    except Exception as e:
        print('ERR', db, e)
PY
echo '== v2 =='
/opt/agentlink/.venv/bin/python - <<'PY'
import json
from pathlib import Path
for p in Path('/opt/agentlink/data/v2_threads').glob('*.json'):
    d=json.loads(p.read_text(encoding='utf-8'))
    print('threads', p.name, len(d.get('threads') or {}))
for p in Path('/opt/agentlink/data/v2_cases').glob('*.json'):
    d=json.loads(p.read_text(encoding='utf-8'))
    print('cases', p.name, len(d.get('cases') or {}))
op=Path('/opt/agentlink/data/v2_orders/orders.json')
if op.exists():
    d=json.loads(op.read_text(encoding='utf-8'))
    print('orders', len(d.get('orders') or {}), 'logistics', len(d.get('logistics') or {}))
PY
"""


def main() -> None:
    for role, host, pem in (
        ("buyer", "81.70.46.119", True),
        ("supplier", "39.105.20.113", False),
    ):
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if pem:
            c.connect(host, username="root", pkey=paramiko.RSAKey.from_private_key_file(str(PEM)), timeout=30, allow_agent=False, look_for_keys=False)
        else:
            c.connect(host, username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
        print(f"===== {role} {host} =====", flush=True)
        _i, o, _e = c.exec_command(CMD, timeout=90, get_pty=True)
        print(o.read().decode("utf-8", "replace")[-4000:], flush=True)
        c.close()


if __name__ == "__main__":
    main()
