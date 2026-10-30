# -*- coding: utf-8 -*-
"""对话线程：保存 / 切换 / 查看历史。"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_ROOT = Path(__file__).resolve().parents[1] / "data" / "v2_threads"
_ROOT.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(agent_id: str) -> Path:
    return _ROOT / f"{agent_id}.json"


def _load(agent_id: str) -> dict[str, Any]:
    p = _path(agent_id)
    if not p.is_file():
        return {"active": None, "threads": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"active": None, "threads": {}}


def _save(agent_id: str, data: dict[str, Any]) -> None:
    _path(agent_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _public(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": t["id"],
        "title": t.get("title") or t["id"],
        "status": t.get("status") or "open",
        "created_at": t.get("created_at"),
        "updated_at": t.get("updated_at"),
        "case_id": t.get("case_id"),
        "message_count": len(t.get("messages") or []),
        "preview": _preview(t),
    }


def _preview(t: dict[str, Any]) -> str:
    msgs = t.get("messages") or []
    for m in reversed(msgs):
        if (m.get("role") or "") == "user":
            return str(m.get("content") or m.get("text") or "")[:48]
    return ""


def list_threads(agent_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        data = _load(agent_id)
        items = [
            _public(t)
            for t in data.get("threads", {}).values()
            if (t.get("status") or "open") != "deleted"
        ]
        items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return items[:limit]


def get_thread(agent_id: str, thread_id: str) -> dict[str, Any] | None:
    with _LOCK:
        t = _load(agent_id).get("threads", {}).get(thread_id)
        return json.loads(json.dumps(t)) if t and t.get("status") != "deleted" else None


def active_thread_id(agent_id: str) -> str | None:
    with _LOCK:
        data = _load(agent_id)
        aid = data.get("active")
        if aid and aid in data.get("threads", {}) and data["threads"][aid].get("status") != "deleted":
            return aid
        items = list_threads(agent_id, limit=1)
        return items[0]["id"] if items else None


def create_thread(agent_id: str, *, title: str | None = None, case_id: str | None = None) -> dict[str, Any]:
    with _LOCK:
        data = _load(agent_id)
        tid = f"th-{uuid.uuid4().hex[:10]}"
        now = _now()
        title = (title or "").strip() or f"对话 {now[5:16].replace('T', ' ')}"
        row = {
            "id": tid,
            "title": title,
            "status": "open",
            "created_at": now,
            "updated_at": now,
            "case_id": case_id,
            "messages": [],
        }
        data.setdefault("threads", {})[tid] = row
        data["active"] = tid
        _save(agent_id, data)
        return _public(row)


def ensure_thread(agent_id: str, thread_id: str | None = None) -> dict[str, Any]:
    with _LOCK:
        data = _load(agent_id)
        tid = (thread_id or data.get("active") or "").strip()
        if tid and tid in data.get("threads", {}) and data["threads"][tid].get("status") != "deleted":
            data["active"] = tid
            _save(agent_id, data)
            return _public(data["threads"][tid])
        # 复用最近一条
        opens = [
            t
            for t in data.get("threads", {}).values()
            if (t.get("status") or "open") != "deleted"
        ]
        opens.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        if opens:
            data["active"] = opens[0]["id"]
            _save(agent_id, data)
            return _public(opens[0])
    return create_thread(agent_id, title="默认对话")


def activate(agent_id: str, thread_id: str) -> dict[str, Any]:
    with _LOCK:
        data = _load(agent_id)
        t = data.get("threads", {}).get(thread_id)
        if not t or t.get("status") == "deleted":
            raise KeyError(thread_id)
        data["active"] = thread_id
        t["updated_at"] = _now()
        _save(agent_id, data)
        return {
            "ok": True,
            "thread_id": thread_id,
            "case_id": t.get("case_id"),
            "id": thread_id,
        }


def delete_thread(agent_id: str, thread_id: str) -> dict[str, Any]:
    with _LOCK:
        data = _load(agent_id)
        t = data.get("threads", {}).get(thread_id)
        if not t:
            raise KeyError(thread_id)
        t["status"] = "deleted"
        t["updated_at"] = _now()
        if data.get("active") == thread_id:
            data["active"] = None
            for other in sorted(
                (x for x in data["threads"].values() if x.get("status") != "deleted"),
                key=lambda x: x.get("updated_at") or "",
                reverse=True,
            ):
                data["active"] = other["id"]
                break
        _save(agent_id, data)
        return {"ok": True, "deleted": thread_id, "active_thread_id": data.get("active")}


def bind_case(agent_id: str, thread_id: str, case_id: str) -> None:
    with _LOCK:
        data = _load(agent_id)
        t = data.get("threads", {}).get(thread_id)
        if not t:
            return
        t["case_id"] = case_id
        t["updated_at"] = _now()
        _save(agent_id, data)


def append_messages(agent_id: str, thread_id: str, messages: list[dict[str, Any]]) -> None:
    if not messages:
        return
    with _LOCK:
        data = _load(agent_id)
        t = data.get("threads", {}).get(thread_id)
        if not t:
            return
        t.setdefault("messages", []).extend(messages)
        # 首条用户消息自动改标题
        title = t.get("title") or ""
        if title.startswith("对话 ") or title in ("默认对话", "v2 主对话", "新对话"):
            for m in messages:
                if m.get("role") == "user":
                    text = str(m.get("content") or m.get("text") or "").strip()
                    if text:
                        t["title"] = text[:28] + ("…" if len(text) > 28 else "")
                    break
        t["updated_at"] = _now()
        data["active"] = thread_id
        _save(agent_id, data)


def list_messages(agent_id: str, thread_id: str | None = None, *, limit: int = 200) -> tuple[str | None, list[dict[str, Any]]]:
    with _LOCK:
        data = _load(agent_id)
        tid = (thread_id or data.get("active") or "").strip()
        if not tid or tid not in data.get("threads", {}):
            return None, []
        t = data["threads"][tid]
        if t.get("status") == "deleted":
            return tid, []
        msgs = list(t.get("messages") or [])[-limit:]
        return tid, json.loads(json.dumps(msgs))
