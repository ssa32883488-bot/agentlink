# -*- coding: utf-8 -*-
"""仅清空对话历史 + 工单；不动库存/目录/邮箱/配置。"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

REMOTE_PY = r'''
import json, sqlite3
from pathlib import Path

root = Path("/opt/agentlink")
data = root / "data"
report = {"files": [], "sqlite": [], "kept_hint": "inventory/catalog/mailbox/config untouched"}

# --- v2 JSON stores ---
for rel, empty in [
    ("v2_threads", None),  # wipe all agent json
    ("v2_cases", None),
    ("v2_orders", {"orders": {}, "logistics": {}}),
]:
    d = data / rel
    d.mkdir(parents=True, exist_ok=True)
    if rel == "v2_orders":
        p = d / "orders.json"
        p.write_text(json.dumps(empty, ensure_ascii=False, indent=2), encoding="utf-8")
        report["files"].append(str(p))
    else:
        for p in d.glob("*.json"):
            if rel == "v2_threads":
                p.write_text(json.dumps({"active": None, "threads": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                p.write_text(json.dumps({"active": None, "cases": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
            report["files"].append(str(p))

# legacy procurement cases json
for p in data.glob("procurement_cases_*.json"):
    p.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")
    report["files"].append(str(p))

# --- sqlite: only history + tickets tables ---
CLEAR_SQL = """
DELETE FROM ticket_events;
DELETE FROM work_tickets;
DELETE FROM conversations;
DELETE FROM chat_threads;
"""
# optional: shared_facts tied to chat
OPTIONAL = "DELETE FROM shared_facts;"

for db in sorted(data.glob("*.sqlite3")):
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        cleared = []
        for stmt in CLEAR_SQL.strip().split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            t = stmt.split()[-1]
            if t in tables:
                cur.execute(stmt)
                cleared.append(t)
        if "shared_facts" in tables:
            cur.execute(OPTIONAL)
            cleared.append("shared_facts")
        conn.commit()
        conn.close()
        report["sqlite"].append({"db": db.name, "cleared": cleared})
    except Exception as e:
        report["sqlite"].append({"db": db.name, "error": str(e)[:200]})

# also agentlink_bundle copy if present
bundle = Path("/opt/agentlink_bundle/agentlink/data")
if bundle.is_dir():
    for sub in ("v2_threads", "v2_cases", "v2_orders"):
        d = bundle / sub
        if not d.is_dir():
            continue
        if sub == "v2_orders":
            (d / "orders.json").write_text(json.dumps({"orders": {}, "logistics": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            for p in d.glob("*.json"):
                payload = {"active": None, "threads": {}} if sub == "v2_threads" else {"active": None, "cases": {}}
                p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

print("CLEAR_OK", json.dumps(report, ensure_ascii=False))
'''


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect("39.105.20.113", username="root", password=PW, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    print("$", cmd[:140], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=120, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out[-2500:], flush=True)
    return out


def clear_host(role: str) -> None:
    c = connect(role)
    remote = f"/tmp/clear_hist_tickets_{role}.py"
    sftp = c.open_sftp()
    with sftp.file(remote, "w") as f:
        f.write(REMOTE_PY)
    sftp.close()
    run(c, f"/opt/agentlink/.venv/bin/python {remote}")
    # soft restart so in-memory caches drop
    if role == "buyer":
        run(
            c,
            "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics 2>/dev/null; sleep 2; "
            "systemctl is-active agentlink-buyer-a",
        )
        run(
            c,
            "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
            "import json; from pathlib import Path\n"
            "from commerce_v2 import order_ids, thread_store\n"
            "d=order_ids._load();\n"
            "print('orders', len(d.get('orders') or {}), 'logistics', len(d.get('logistics') or {}))\n"
            "print('threads_buyer_a', len(thread_store.list_threads('buyer-a')))\n"
            "PY",
        )
    else:
        run(
            c,
            "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c 2>/dev/null; sleep 2; "
            "systemctl is-active agentlink-supplier-a",
        )
    c.close()


def clear_local() -> None:
    root = Path(__file__).resolve().parents[1]
    data = root / "data"
    if not data.is_dir():
        print("LOCAL_SKIP no data dir", flush=True)
        return
    for p in (data / "v2_threads").glob("*.json"):
        p.write_text(json.dumps({"active": None, "threads": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("local", p, flush=True)
    for p in (data / "v2_cases").glob("*.json"):
        p.write_text(json.dumps({"active": None, "cases": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("local", p, flush=True)
    op = data / "v2_orders" / "orders.json"
    if op.parent.is_dir():
        op.write_text(json.dumps({"orders": {}, "logistics": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("local", op, flush=True)
    for p in data.glob("procurement_cases_*.json"):
        p.write_text("{}\n", encoding="utf-8")
        print("local", p, flush=True)
    for db in data.glob("*.sqlite3"):
        conn = sqlite3.connect(str(db))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("ticket_events", "work_tickets", "conversations", "chat_threads", "shared_facts"):
            if t in tables:
                conn.execute(f"DELETE FROM {t}")
        conn.commit()
        conn.close()
        print("local sqlite", db.name, flush=True)
    print("LOCAL_CLEAR_OK", flush=True)


def main() -> None:
    clear_local()
    print("=== BUYER CLOUD ===", flush=True)
    clear_host("buyer")
    print("=== SUPPLIER CLOUD ===", flush=True)
    clear_host("supplier")
    print("ALL_CLEAR_DONE", flush=True)


if __name__ == "__main__":
    main()
