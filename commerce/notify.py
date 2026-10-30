"""全智能体通用通知。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from commerce.db import dumps, ensure_agent_db, lock_for, row_to_dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def push(
    agent_id: str,
    *,
    title: str,
    body: str,
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nid = f"NTF-{uuid4().hex[:10]}"
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            """
            INSERT INTO notifications(id, created_at, level, title, body, payload_json, read)
            VALUES(?,?,?,?,?,?,0)
            """,
            (nid, _now(), level, title, body, dumps(payload or {})),
        )
        conn.commit()
        conn.close()
    return {"id": nid, "title": title, "level": level, "body": body, "payload": payload or {}}


def list_notifications(agent_id: str, *, unread_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        if unread_only:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE read=0 ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
    out = []
    for r in rows:
        d = row_to_dict(r)
        if not d:
            continue
        if d.get("payload_json"):
            try:
                d["payload"] = json.loads(d["payload_json"])
            except Exception:
                d["payload"] = None
        out.append(d)
    return out


def mark_read(agent_id: str, nid: str) -> None:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute("UPDATE notifications SET read=1 WHERE id=?", (nid,))
        conn.commit()
        conn.close()
