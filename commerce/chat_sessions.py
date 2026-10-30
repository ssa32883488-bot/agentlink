"""多对话窗口：窗口记忆隔离，关键事实跨窗共享。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from commerce.db import dumps, ensure_agent_db, lock_for, row_to_dict

_ACTIVE_THREAD: dict[str, str] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_active_thread(agent_id: str, thread_id: str | None) -> None:
    if thread_id:
        _ACTIVE_THREAD[agent_id] = thread_id
    else:
        _ACTIVE_THREAD.pop(agent_id, None)


def active_thread_id(agent_id: str) -> str | None:
    return _ACTIVE_THREAD.get(agent_id)


def list_threads(agent_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        rows = conn.execute(
            "SELECT * FROM chat_threads WHERE status!='deleted' ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
    return [row_to_dict(r) for r in rows if r]  # type: ignore[misc]


def get_thread(agent_id: str, thread_id: str) -> dict[str, Any] | None:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        row = row_to_dict(conn.execute("SELECT * FROM chat_threads WHERE id=?", (thread_id,)).fetchone())
        conn.close()
    return row


def create_thread(agent_id: str, *, title: str | None = None) -> dict[str, Any]:
    tid = f"th-{uuid4().hex[:10]}"
    now = _now()
    title = (title or "").strip() or f"对话 {now[5:16].replace('T', ' ')}"
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            "INSERT INTO chat_threads(id, created_at, updated_at, title, status, meta_json) VALUES(?,?,?,?,?,?)",
            (tid, now, now, title, "open", dumps({})),
        )
        conn.commit()
        conn.close()
    set_active_thread(agent_id, tid)
    return get_thread(agent_id, tid) or {"id": tid, "title": title, "status": "open"}


def ensure_thread(agent_id: str, thread_id: str | None = None) -> str:
    """返回可用 thread_id；无则新建。"""
    tid = (thread_id or active_thread_id(agent_id) or "").strip()
    if tid and get_thread(agent_id, tid):
        set_active_thread(agent_id, tid)
        return tid
    threads = list_threads(agent_id, limit=1)
    if threads:
        set_active_thread(agent_id, threads[0]["id"])
        return str(threads[0]["id"])
    return str(create_thread(agent_id)["id"])


def touch_thread(agent_id: str, thread_id: str, *, title: str | None = None) -> None:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        if title:
            conn.execute(
                "UPDATE chat_threads SET updated_at=?, title=? WHERE id=?",
                (_now(), title, thread_id),
            )
        else:
            conn.execute("UPDATE chat_threads SET updated_at=? WHERE id=?", (_now(), thread_id))
        conn.commit()
        conn.close()


def delete_thread(agent_id: str, thread_id: str) -> None:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute("UPDATE chat_threads SET status='deleted', updated_at=? WHERE id=?", (_now(), thread_id))
        conn.commit()
        conn.close()
    if active_thread_id(agent_id) == thread_id:
        set_active_thread(agent_id, None)


# —— 共享关键事实 ——


def upsert_shared_fact(
    agent_id: str,
    key: str,
    value: Any,
    *,
    tags: list[str] | None = None,
    source_thread_id: str | None = None,
) -> None:
    key = (key or "").strip()
    if not key:
        return
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            """
            INSERT INTO shared_facts(key, value_json, tags_json, source_thread_id, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              tags_json=excluded.tags_json,
              source_thread_id=excluded.source_thread_id,
              updated_at=excluded.updated_at
            """,
            (key, dumps(value), dumps(tags or []), source_thread_id, _now()),
        )
        conn.commit()
        conn.close()


def list_shared_facts(agent_id: str) -> dict[str, Any]:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        rows = conn.execute("SELECT * FROM shared_facts ORDER BY updated_at DESC").fetchall()
        conn.close()
    out: dict[str, Any] = {}
    for r in rows:
        d = row_to_dict(r)
        if not d:
            continue
        try:
            out[d["key"]] = json.loads(d["value_json"])
        except Exception:
            out[d["key"]] = d["value_json"]
    return out


def get_thread_meta(agent_id: str, thread_id: str) -> dict[str, Any]:
    th = get_thread(agent_id, thread_id)
    if not th:
        return {}
    raw = th.get("meta_json")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def patch_thread_meta(agent_id: str, thread_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    meta = get_thread_meta(agent_id, thread_id)
    meta.update({k: v for k, v in (patch or {}).items() if v is not None})
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            "UPDATE chat_threads SET meta_json=?, updated_at=? WHERE id=?",
            (dumps(meta), _now(), thread_id),
        )
        conn.commit()
        conn.close()
    return meta


def bind_thread_case(
    agent_id: str,
    thread_id: str,
    case_id: str | None,
    *,
    product_name: str | None = None,
) -> None:
    """把采购案绑到当前对话窗，避免串到别的物料案。"""
    if not thread_id:
        return
    patch: dict[str, Any] = {"case_id": case_id}
    if product_name:
        patch["subject_product"] = product_name
    patch_thread_meta(agent_id, thread_id, patch)


def thread_bound_case_id(agent_id: str, thread_id: str | None) -> str | None:
    if not thread_id:
        return None
    meta = get_thread_meta(agent_id, thread_id)
    cid = meta.get("case_id")
    return str(cid) if cid else None


def shared_facts_prompt_block(agent_id: str, *, subject_product: str | None = None) -> str:
    facts = list_shared_facts(agent_id)
    if not facts:
        return ""
    lines = [
        "【跨对话共享关键信息】（各窗口可共用；但必须与本窗当前物料主体一致才可引用）",
        "规则：若某条未标明 SKU/物料，或与用户本窗正在谈的物料不一致，一律忽略，禁止套用数量/预算到错误主体。",
    ]
    if subject_product:
        lines.append(f"本窗当前主体物料：{subject_product}")
    for k, v in list(facts.items())[:40]:
        text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        if subject_product:
            # 粗过滤：值或 key 里完全看不到主体时，标注「需核对」
            blob = f"{k} {text}"
            if subject_product not in blob and "product" not in k.lower() and "sku" not in k.lower():
                lines.append(f"- {k}: {text}  ※未绑定物料，引用前须向用户确认是否属于「{subject_product}」")
                continue
        lines.append(f"- {k}: {text}")
    return "\n".join(lines)
