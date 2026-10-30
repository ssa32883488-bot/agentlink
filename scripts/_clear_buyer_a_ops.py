# -*- coding: utf-8 -*-
"""清空采购商A业务数据（对话/审计/通知/订单/工单/邮件/采购案/记忆），保留系统日志与主数据。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE = r"""
set -e
cd /opt/agentlink
/opt/agentlink/.venv/bin/python <<'PY'
from pathlib import Path
import sqlite3

root = Path('/opt/agentlink')
db = root / 'data' / 'buyer-a.sqlite3'
print('db', db, 'exists', db.exists())
if db.exists():
    conn = sqlite3.connect(str(db))
    tables = [
        'conversations', 'notifications', 'audit_tasks',
        'sales_order_lines', 'sales_orders',
        'mailbox', 'ticket_events', 'work_tickets',
        'chat_threads', 'shared_facts',
    ]
    for t in tables:
        try:
            n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            conn.execute(f'DELETE FROM {t}')
            print(f'cleared {t}: {n}')
        except Exception as e:
            print(f'skip {t}: {e}')
    conn.commit()
    conn.close()

# 采购案 JSON（结构必须是 {"cases": {}}，不能写成 []）
empty_cases = '{"cases": {}}'
for p in (root / 'data').glob('procurement_cases*buyer-a*'):
    p.write_text(empty_cases, encoding='utf-8')
    print('cleared', p.name)
legacy = root / 'data' / 'procurement_cases.json'
if legacy.exists():
    legacy.write_text(empty_cases, encoding='utf-8')
    print('cleared procurement_cases.json')

# 案件记忆文件（buyer-a）
mem = root / 'data' / 'agent_memory'
if mem.is_dir():
    for p in mem.glob('buyer-a_*.json'):
        p.unlink()
        print('rm memory', p.name)
    for p in mem.glob('*.json'):
        # 旧命名无 agent 前缀：一并清，避免串窗
        if p.name.startswith('case') or 'buyer' in p.name.lower():
            p.unlink(missing_ok=True)
            print('rm memory', p.name)

# Wit 窗口工作区（不清系统 logs/）
ws = root / 'workspaces' / 'buyer-a-wit'
if ws.is_dir():
    import shutil
    for child in ws.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            print('rm workspace', child.name)
        elif child.suffix in ('.json', '.jsonl', '.db', '.sqlite'):
            child.unlink(missing_ok=True)
            print('rm workspace file', child.name)

print('KEEP logs/, inventory/products/materials/bom')
print('CLEAR_BUYER_A_DONE')
PY
systemctl restart agentlink-buyer-a
sleep 3
systemctl is-active agentlink-buyer-a
curl -sk https://127.0.0.1:8010/api/erp/conversations | head -c 120; echo
curl -sk https://127.0.0.1:8010/api/erp/notifications | head -c 120; echo
curl -sk https://127.0.0.1:8010/api/erp/sales-orders | head -c 120; echo
"""


def main() -> None:
    # also deploy code first
    files = [
        "commerce/db.py",
        "commerce/chat_sessions.py",
        "commerce/buyer_service.py",
        "commerce/buyer_routes.py",
        "commerce/buyer_tools/memory_store.py",
        "commerce/buyer_tools/service.py",
        "commerce/chat_buyer_wit.py",
        "ui/static/app.js",
        "ui/static/index.html",
        "ui/static/styles.css",
    ]
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
    for rel in files:
        remote = f"/opt/agentlink/{rel}"
        parent = remote.rsplit("/", 1)[0]
        _, o, _ = b.exec_command(f"mkdir -p {parent}")
        o.channel.recv_exit_status()
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()
    _, o, e = b.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b "
        "agentlink-ui-buyer-a agentlink-ui-buyer-b; sleep 4; " + REMOTE,
        timeout=180,
        get_pty=True,
    )
    sys.stdout.buffer.write(o.read() + e.read() + b"\n")
    b.close()


if __name__ == "__main__":
    main()
