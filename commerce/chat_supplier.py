"""供应商对话辅助：会话落库 / 线程；对话编排已迁至 chat_supplier_wit（Wit+DeepSeek）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from commerce import chat_sessions as cs
from commerce.db import dumps, ensure_agent_db, lock_for

_AGENT_ID = "supplier-a"


def configure(*, agent_id: str) -> None:
    global _AGENT_ID
    _AGENT_ID = agent_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_conv(
    agent_id: str,
    role: str,
    content: str,
    *,
    thread_id: str | None = None,
    meta: dict | None = None,
) -> None:
    ensure_agent_db(agent_id).close()
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
        cid = f"cv-{uuid4().hex[:10]}"
        if "thread_id" in cols:
            conn.execute(
                "INSERT INTO conversations(id,created_at,role,content,meta_json,thread_id) VALUES(?,?,?,?,?,?)",
                (cid, _now(), role, content, dumps(meta or {}), thread_id),
            )
        else:
            conn.execute(
                "INSERT INTO conversations(id,created_at,role,content,meta_json) VALUES(?,?,?,?,?)",
                (cid, _now(), role, content, dumps(meta or {})),
            )
        conn.commit()
        conn.close()
    if thread_id:
        cs.touch_thread(agent_id, thread_id)


def list_conversations(agent_id: str, *, thread_id: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
        if "thread_id" in cols and thread_id:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE thread_id=? ORDER BY created_at ASC LIMIT ?",
                (thread_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
    from commerce.db import row_to_dict

    items = [row_to_dict(r) for r in rows if r]
    if "thread_id" not in cols or not thread_id:
        items = list(reversed(items))
    return [i for i in items if i]
