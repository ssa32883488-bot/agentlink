# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _i, o, e = c.exec_command(cmd, timeout=90)
    return (o.read() + e.read()).decode("utf-8", errors="replace").strip()


def main() -> None:
    c = connect()
    print("=== active thread detail ===")
    print(
        run(
            c,
            r"""python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path('/opt/agentlink/data/v2_threads/buyer-a.json').read_text())
aid=d.get('active')
print('active', aid)
t=(d.get('threads') or {}).get(aid) or {}
print('title', t.get('title'), 'msgs', len(t.get('messages') or []), 'case', t.get('case_id'), 'status', t.get('status'))
for m in (t.get('messages') or [])[-6:]:
    print(m.get('role'), str(m.get('content') or '')[:100].replace('\n',' '))
# find threads mentioning 面料 / 1000
for tid,t in (d.get('threads') or {}).items():
    title=str(t.get('title') or '')
    preview=''
    for m in t.get('messages') or []:
        if m.get('role')=='user':
            preview=str(m.get('content') or '')
            break
    if '面料' in title or '面料' in preview or '1000' in title or '1000' in preview:
        print('HIT', tid, 'title=', title, 'msgs=', len(t.get('messages') or []), 'case=', t.get('case_id'), 'status=', t.get('status'))
        print('  preview=', preview[:80])
PY"""
        )
    )
    print("=== curl buyer-a conversations ===")
    print(
        run(
            c,
            "curl -sS -m 8 http://127.0.0.1:8010/api/erp/conversations 2>&1 | head -c 500; echo; "
            "curl -sk -m 8 https://127.0.0.1:8010/api/erp/conversations 2>&1 | head -c 500; echo; "
            "curl -sS -m 8 http://127.0.0.1:8010/api/erp/chat/threads 2>&1 | head -c 500; echo; "
            "curl -sk -m 8 https://127.0.0.1:8010/openapi.json 2>&1 | python3 -c 'import sys,json; d=json.load(sys.stdin); print([p for p in d.get(\"paths\",{}) if \"conversation\" in p or \"thread\" in p or \"chat\" in p][:40])' 2>&1",
        )
    )
    print("=== how buyer mounts routes ===")
    print(
        run(
            c,
            "grep -n 'commerce_v2\\|mount\\|conversations\\|use_v2\\|include_router' "
            "/opt/agentlink/agents/buyer_a/main.py /opt/agentlink/commerce_v2/runtime_flag.py "
            "/opt/agentlink/commerce_v2/__init__.py 2>/dev/null | head -60; "
            "systemctl cat agentlink-buyer-a --no-pager | head -40; "
            "echo ENV; systemctl show agentlink-buyer-a -p Environment --no-pager",
        )
    )
    print("=== ui proxy conversations ===")
    print(
        run(
            c,
            "curl -sk -m 8 'https://127.0.0.1:8090/api/proxy/buyer-a/api/erp/conversations' 2>&1 | head -c 800; echo; "
            "curl -sk -m 8 'https://127.0.0.1:8090/api/proxy/buyer-a/api/erp/chat/threads' 2>&1 | head -c 800; echo; "
            "grep -n 'proxy\\|conversations' /opt/agentlink/ui/app.py | head -40",
        )
    )
    c.close()


if __name__ == "__main__":
    main()
