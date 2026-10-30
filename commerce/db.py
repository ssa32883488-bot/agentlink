from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_LOCKS: dict[str, threading.Lock] = {}
_ROOT = Path(__file__).resolve().parents[1] / "data"


def db_path(agent_id: str) -> Path:
    _ROOT.mkdir(parents=True, exist_ok=True)
    return _ROOT / f"{agent_id}.sqlite3"


def connect(agent_id: str) -> sqlite3.Connection:
    path = db_path(agent_id)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def lock_for(agent_id: str) -> threading.Lock:
    if agent_id not in _LOCKS:
        _LOCKS[agent_id] = threading.Lock()
    return _LOCKS[agent_id]


OFFICE_SCHEMA = """
        CREATE TABLE IF NOT EXISTS mailbox (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          direction TEXT NOT NULL,
          folder TEXT NOT NULL,
          mail_kind TEXT NOT NULL,
          subject TEXT NOT NULL,
          body TEXT NOT NULL,
          from_agent TEXT,
          from_email TEXT,
          to_agent TEXT,
          to_email TEXT,
          ticket_id TEXT,
          attachment_json TEXT,
          read INTEGER DEFAULT 0,
          acked INTEGER DEFAULT 0,
          meta_json TEXT
        );
        CREATE TABLE IF NOT EXISTS work_tickets (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          title TEXT NOT NULL,
          kind TEXT NOT NULL,
          status TEXT NOT NULL,
          peer_agent_id TEXT,
          peer_email TEXT,
          case_id TEXT,
          state_json TEXT,
          order_mail_id TEXT,
          invoice_mail_id TEXT,
          order_recv_self INTEGER DEFAULT 0,
          order_recv_peer INTEGER DEFAULT 0,
          invoice_recv_self INTEGER DEFAULT 0,
          invoice_recv_peer INTEGER DEFAULT 0,
          archived_at TEXT,
          detail_json TEXT
        );
        CREATE TABLE IF NOT EXISTS ticket_events (
          id TEXT PRIMARY KEY,
          ticket_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          event TEXT NOT NULL,
          actor TEXT,
          detail_json TEXT,
          FOREIGN KEY(ticket_id) REFERENCES work_tickets(id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          level TEXT NOT NULL,
          title TEXT NOT NULL,
          body TEXT NOT NULL,
          payload_json TEXT,
          read INTEGER DEFAULT 0
        );
"""


CHAT_SCHEMA = """
        CREATE TABLE IF NOT EXISTS chat_threads (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          title TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS shared_facts (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL,
          tags_json TEXT,
          source_thread_id TEXT,
          updated_at TEXT NOT NULL
        );
"""


CHAT_SESSION_SCHEMA = """
        CREATE TABLE IF NOT EXISTS chat_threads (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          title TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'open',
          meta_json TEXT
        );
        CREATE TABLE IF NOT EXISTS shared_facts (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL,
          tags_json TEXT,
          source_thread_id TEXT,
          updated_at TEXT NOT NULL
        );
"""


def init_office_schema(conn: sqlite3.Connection) -> None:
    """邮箱 / 工单 / 审计事件 — 所有智能体共用。"""
    conn.executescript(OFFICE_SCHEMA)
    conn.commit()


def init_chat_session_schema(conn: sqlite3.Connection) -> None:
    """多对话窗口 + 跨窗共享关键事实。"""
    conn.executescript(CHAT_SESSION_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    if cols and "thread_id" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN thread_id TEXT")
    conn.commit()
    init_chat_schema(conn)


def init_chat_schema(conn: sqlite3.Connection) -> None:
    """多对话窗口 + 跨窗共享关键事实。"""
    conn.executescript(CHAT_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    if cols and "thread_id" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN thread_id TEXT")
    conn.commit()


def init_buyer_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
          sku TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          price REAL NOT NULL,
          description TEXT,
          active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS materials (
          code TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          unit TEXT NOT NULL,
          preferred_supplier TEXT,
          safety_stock REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bom (
          finished_sku TEXT NOT NULL,
          material_code TEXT NOT NULL,
          qty_per REAL NOT NULL,
          PRIMARY KEY (finished_sku, material_code)
        );
        CREATE TABLE IF NOT EXISTS inventory (
          material_code TEXT PRIMARY KEY,
          on_hand REAL NOT NULL DEFAULT 0,
          reserved REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sales_orders (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          customer_name TEXT,
          sku TEXT NOT NULL,
          qty INTEGER NOT NULL,
          amount REAL NOT NULL,
          status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sales_order_lines (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          order_id TEXT NOT NULL,
          material_code TEXT NOT NULL,
          need_qty REAL NOT NULL,
          FOREIGN KEY(order_id) REFERENCES sales_orders(id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          level TEXT NOT NULL,
          title TEXT NOT NULL,
          body TEXT NOT NULL,
          payload_json TEXT,
          read INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS conversations (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          meta_json TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_tasks (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          kind TEXT NOT NULL,
          title TEXT NOT NULL,
          status TEXT NOT NULL,
          detail_json TEXT
        );
        """
    )
    conn.commit()
    init_office_schema(conn)
    init_chat_session_schema(conn)


def init_supplier_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS catalog (
          code TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          unit TEXT NOT NULL,
          list_price REAL NOT NULL,
          floor_price REAL NOT NULL,
          on_hand REAL NOT NULL,
          strategy_tag TEXT,
          moq REAL DEFAULT 1,
          lead_time_days INTEGER DEFAULT 5
        );
        CREATE TABLE IF NOT EXISTS rfq_inbox (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          business_id TEXT,
          buyer_ref TEXT,
          material_code TEXT,
          qty REAL,
          status TEXT,
          request_json TEXT,
          response_json TEXT
        );
        CREATE TABLE IF NOT EXISTS conversations (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          meta_json TEXT,
          thread_id TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_tasks (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          kind TEXT NOT NULL,
          title TEXT NOT NULL,
          status TEXT NOT NULL,
          detail_json TEXT
        );
        """
    )
    conn.commit()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
        if "thread_id" not in cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN thread_id TEXT")
            conn.commit()
    except Exception:
        pass
    init_office_schema(conn)
    init_chat_session_schema(conn)


def ensure_agent_db(agent_id: str) -> sqlite3.Connection:
    """任意智能体库：至少具备 office 表。"""
    conn = connect(agent_id)
    if agent_id.startswith("buyer"):
        init_buyer_schema(conn)
    elif agent_id.startswith("supplier"):
        init_supplier_schema(conn)
    else:
        init_office_schema(conn)
        init_chat_session_schema(conn)
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
