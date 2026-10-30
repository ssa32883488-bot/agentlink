# -*- coding: utf-8 -*-
"""清空六智能体历史：对话 / 通知 / 邮件 / 订单 / 工单 / 审计 / 采购案 / 记忆。

保留：库存、价目、产品、BOM、物料等主数据；系统 logs/。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

AGENTS_TENCENT = ("buyer-a", "buyer-b", "logistics")
AGENTS_ALIYUN = ("supplier-a", "supplier-b", "supplier-c")

CLEAR_TABLES = (
    "conversations",
    "chat_threads",
    "work_tickets",
    "ticket_events",
    "notifications",
    "shared_facts",
    "mailbox",
    "sales_order_lines",
    "sales_orders",
    "audit_tasks",
    "rfq_inbox",
)


def _remote_script(agents: tuple[str, ...], restart_units: tuple[str, ...]) -> str:
    return (
        "import json, sqlite3, shutil\n"
        "from pathlib import Path\n"
        "data = Path('/opt/agentlink/data')\n"
        f"agents = {json.dumps(list(agents), ensure_ascii=False)}\n"
        f"CLEAR_TABLES = {json.dumps(list(CLEAR_TABLES), ensure_ascii=False)}\n"
        "report = []\n"
        "for aid in agents:\n"
        "    db = data / (aid + '.sqlite3')\n"
        "    if not db.is_file():\n"
        "        report.append({'agent': aid, 'skipped': True}); continue\n"
        "    conn = sqlite3.connect(str(db))\n"
        "    existing = {r[0] for r in conn.execute("
        "\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()}\n"
        "    before = {}\n"
        "    for t in CLEAR_TABLES:\n"
        "        if t in existing:\n"
        "            before[t] = conn.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]\n"
        "    # children first\n"
        "    for t in ('ticket_events','sales_order_lines','work_tickets','sales_orders',"
        "'conversations','chat_threads','notifications','shared_facts','mailbox',"
        "'audit_tasks','rfq_inbox'):\n"
        "        if t in existing: conn.execute('DELETE FROM %s' % t)\n"
        "    conn.commit()\n"
        "    after = {}\n"
        "    for t in CLEAR_TABLES:\n"
        "        if t in existing:\n"
        "            after[t] = conn.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]\n"
        "    conn.close()\n"
        "    report.append({'agent': aid, 'before': before, 'after': after})\n"
        "empty_cases = '{\"cases\": {}}\\n'\n"
        "for p in data.glob('procurement_cases*.json'):\n"
        "    p.write_text(empty_cases, encoding='utf-8')\n"
        "    report.append({'cleared_cases_file': p.name})\n"
        "mem = data / 'agent_memory'\n"
        "n_mem = 0\n"
        "if mem.is_dir():\n"
        "    for f in mem.glob('*.json'):\n"
        "        f.unlink(missing_ok=True); n_mem += 1\n"
        "report.append({'agent_memory_files_removed': n_mem})\n"
        "ws_root = Path('/opt/agentlink/workspaces')\n"
        "n_ws = 0\n"
        "if ws_root.is_dir():\n"
        "    for aid in agents:\n"
        "        for pattern in (aid + '-wit', aid + '_wit', aid):\n"
        "            ws = ws_root / pattern\n"
        "            if not ws.is_dir(): continue\n"
        "            for child in list(ws.iterdir()):\n"
        "                if child.is_dir():\n"
        "                    shutil.rmtree(child, ignore_errors=True); n_ws += 1\n"
        "                elif child.suffix in ('.json','.jsonl','.db','.sqlite','.sqlite3'):\n"
        "                    child.unlink(missing_ok=True); n_ws += 1\n"
        "report.append({'workspace_items_removed': n_ws})\n"
        "print('PURGE_REPORT ' + json.dumps(report, ensure_ascii=False))\n"
        f"import subprocess\n"
        f"units = {json.dumps(list(restart_units), ensure_ascii=False)}\n"
        "if units:\n"
        "    subprocess.run(['systemctl','restart',*units], check=False)\n"
        "    print('RESTARTED', ' '.join(units))\n"
    )


def run(host: str, agents: tuple[str, ...], units: tuple[str, ...], *, pem: bool) -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = {
        "hostname": host,
        "username": "root",
        "timeout": 40,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    remote = f"/tmp/purge_all_history_{os.getpid()}.py"
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(_remote_script(agents, units))
    sftp.close()
    cmd = f"cd /opt/agentlink && .venv/bin/python {remote}"
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", "replace")
    print(f"==== {host} ====", flush=True)
    print(out, flush=True)
    c.close()


def main() -> None:
    run(
        "81.70.46.119",
        AGENTS_TENCENT,
        ("agentlink-buyer-a", "agentlink-buyer-b", "agentlink-logistics"),
        pem=True,
    )
    run(
        "39.105.20.113",
        AGENTS_ALIYUN,
        (
            "agentlink-supplier-a",
            "agentlink-supplier-b",
            "agentlink-supplier-c",
        ),
        pem=False,
    )
    print("PURGE_ALL_HISTORY_DONE", flush=True)


if __name__ == "__main__":
    main()
