# -*- coding: utf-8 -*-
"""Repair open order tickets whose title still embeds combo brief product names."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE = r"""
cd /opt/agentlink
.venv/bin/python - <<'PY'
import json
from commerce.db import ensure_agent_db, lock_for, dumps

def repair(agent_id: str) -> int:
    n = 0
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        rows = conn.execute(
            "SELECT id, title, state_json FROM work_tickets WHERE kind='order' AND status='open'"
        ).fetchall()
        for tid, title, state_json in rows:
            try:
                st = json.loads(state_json or '{}')
            except Exception:
                continue
            summary = st.get('summary') if isinstance(st.get('summary'), dict) else {}
            draft = summary.get('order_draft') if isinstance(summary.get('order_draft'), dict) else {}
            # also accept nested payload
            if 'product_name' not in draft and isinstance(draft.get('payload'), dict):
                draft = draft['payload']
            dname = draft.get('product_name')
            dqty = draft.get('quantity')
            dsku = draft.get('sku')
            if not dname:
                continue
            old_name = str(summary.get('product_name') or '')
            # only rewrite when title/summary still looks like a combo dump
            looks_combo = ('+' in old_name) or ('面料' in old_name and '脚轮' in old_name) or ('+' in (title or ''))
            if not looks_combo and old_name == dname:
                continue
            summary['product_name'] = dname
            if dqty is not None:
                summary['quantity'] = dqty
            if dsku:
                summary['sku'] = dsku
            st['summary'] = summary
            buyer = summary.get('buyer_agent_id') or 'buyer-a'
            goods = summary.get('goods_total') or '—'
            if agent_id.startswith('supplier') or agent_id.startswith('sup'):
                new_title = f"销售订单 · {dname} × {dqty if dqty is not None else '?'} · 买方 {buyer} · 货款 {goods}"
            else:
                sid = summary.get('supplier_agent_id') or 'supplier'
                new_title = f"采购订单 · {dname} × {dqty if dqty is not None else '?'} · 供方 {sid}"
            conn.execute(
                "UPDATE work_tickets SET title=?, state_json=?, updated_at=datetime('now') WHERE id=?",
                (new_title, dumps(st), tid),
            )
            n += 1
            print('fixed', agent_id, tid, '->', new_title)
        conn.commit()
        conn.close()
    return n

agents = []
import os
for a in ('buyer-a','buyer-b','supplier-a','supplier-b','supplier-c'):
    # only repair if this host has the agent db
    from pathlib import Path
    # ensure_agent_db creates; prefer checking env AGENT
    agents.append(a)
# Restrict by ROLE hint
role = os.getenv('AGENTLINK_ROLE') or ''
if 'supplier' in role:
    agents = [a for a in agents if a.startswith('supplier')]
elif 'buyer' in role or 'logistics' in role:
    agents = [a for a in agents if a.startswith('buyer')]

# Detect by existing db files
from pathlib import Path
db_root = Path('/opt/agentlink/data')
found = []
for p in db_root.glob('*/erp.sqlite3') if db_root.exists() else []:
    found.append(p.parent.name)
if not found:
    # fallback common layout
    for a in ('buyer-a','buyer-b','supplier-a','supplier-b','supplier-c'):
        try:
            ensure_agent_db(a).close()
            found.append(a)
        except Exception:
            pass
total = 0
for a in sorted(set(found)):
    if not (a.startswith('buyer') or a.startswith('supplier')):
        continue
    total += repair(a)
print('REPAIR_DONE', total)
PY
"""


def run(host: str, *, pem: bool) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = {"hostname": host, "username": "root", "timeout": 40, "allow_agent": False, "look_for_keys": False}
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    _, o, e = c.exec_command(REMOTE, timeout=90)
    print(host, (o.read() + e.read()).decode("utf-8", "replace"))
    c.close()


if __name__ == "__main__":
    print("TENCENT")
    run("81.70.46.119", pem=True)
    print("ALIYUN")
    run("39.105.20.113", pem=False)
