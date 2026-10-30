"""工单：待办 / 挂起续办 / 双方收妥电子订单+发票后回档。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from commerce.db import dumps, ensure_agent_db, lock_for, row_to_dict

# open=待办处理中 · suspended=挂起可续办 · closed=已完结回档
STATUS_OPEN = "open"
STATUS_SUSPENDED = "suspended"
STATUS_CLOSED = "closed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    for key, out in (("state_json", "state"), ("detail_json", "detail")):
        raw = row.get(key)
        if raw:
            try:
                row[out] = json.loads(raw)
            except Exception:
                row[out] = None
        else:
            row[out] = None
    return row


def _add_event(conn, ticket_id: str, event: str, actor: str | None, detail: dict[str, Any] | None = None) -> None:
    conn.execute(
        "INSERT INTO ticket_events(id, ticket_id, created_at, event, actor, detail_json) VALUES(?,?,?,?,?,?)",
        (f"tev-{uuid4().hex[:10]}", ticket_id, _now(), event, actor, dumps(detail) if detail else None),
    )


def create_ticket(
    agent_id: str,
    *,
    title: str,
    kind: str = "procurement",
    peer_agent_id: str | None = None,
    peer_email: str | None = None,
    case_id: str | None = None,
    state: dict[str, Any] | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tid = f"tk-{uuid4().hex[:10]}"
    now = _now()
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            """
            INSERT INTO work_tickets(
              id, created_at, updated_at, title, kind, status,
              peer_agent_id, peer_email, case_id, state_json, detail_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                tid,
                now,
                now,
                title,
                kind,
                STATUS_OPEN,
                peer_agent_id,
                peer_email,
                case_id,
                dumps(state or {}),
                dumps(detail or {}),
            ),
        )
        _add_event(conn, tid, "created", agent_id, {"title": title, "kind": kind})
        conn.commit()
        conn.close()
    return get_ticket(agent_id, tid)  # type: ignore[return-value]


def get_ticket(agent_id: str, ticket_id: str) -> dict[str, Any] | None:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        row = row_to_dict(conn.execute("SELECT * FROM work_tickets WHERE id=?", (ticket_id,)).fetchone())
        conn.close()
    return _parse(row)


def list_tickets(
    agent_id: str,
    *,
    status: str | None = None,
    include_archived: bool = True,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        sql = "SELECT * FROM work_tickets WHERE 1=1"
        args: list[Any] = []
        if status:
            sql += " AND status=?"
            args.append(status)
        elif not include_archived:
            sql += " AND status!=?"
            args.append(STATUS_CLOSED)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(limit)
        rows = [_parse(row_to_dict(r)) for r in conn.execute(sql, args).fetchall()]
        conn.close()
    return [r for r in rows if r]


def list_events(agent_id: str, ticket_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        rows = conn.execute(
            "SELECT * FROM ticket_events WHERE ticket_id=? ORDER BY created_at ASC LIMIT ?",
            (ticket_id, limit),
        ).fetchall()
        conn.close()
    out = []
    for r in rows:
        d = row_to_dict(r)
        if not d:
            continue
        if d.get("detail_json"):
            try:
                d["detail"] = json.loads(d["detail_json"])
            except Exception:
                d["detail"] = None
        out.append(d)
    return out


def save_state(agent_id: str, ticket_id: str, state: dict[str, Any], *, actor: str | None = None) -> dict[str, Any]:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            "UPDATE work_tickets SET state_json=?, updated_at=? WHERE id=?",
            (dumps(state), _now(), ticket_id),
        )
        _add_event(conn, ticket_id, "state_saved", actor or agent_id, {"keys": list(state.keys())})
        conn.commit()
        conn.close()
    return get_ticket(agent_id, ticket_id)  # type: ignore[return-value]


def suspend(agent_id: str, ticket_id: str, *, reason: str = "", state: dict[str, Any] | None = None) -> dict[str, Any]:
    """挂起：固化当前工作状态，便于后续续办。"""
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        row = row_to_dict(conn.execute("SELECT * FROM work_tickets WHERE id=?", (ticket_id,)).fetchone())
        if not row:
            conn.close()
            raise ValueError("工单不存在")
        if row["status"] == STATUS_CLOSED:
            conn.close()
            raise ValueError("已回档工单不可挂起")
        st = state
        if st is None and row.get("state_json"):
            try:
                st = json.loads(row["state_json"])
            except Exception:
                st = {}
        conn.execute(
            "UPDATE work_tickets SET status=?, state_json=?, updated_at=? WHERE id=?",
            (STATUS_SUSPENDED, dumps(st or {}), _now(), ticket_id),
        )
        _add_event(conn, ticket_id, "suspended", agent_id, {"reason": reason})
        conn.commit()
        conn.close()
    return get_ticket(agent_id, ticket_id)  # type: ignore[return-value]


def resume(agent_id: str, ticket_id: str) -> dict[str, Any]:
    """续办：读取挂起时的工作状态并重新打开。"""
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        row = row_to_dict(conn.execute("SELECT * FROM work_tickets WHERE id=?", (ticket_id,)).fetchone())
        if not row:
            conn.close()
            raise ValueError("工单不存在")
        if row["status"] == STATUS_CLOSED:
            conn.close()
            raise ValueError("已回档工单不可续办")
        conn.execute(
            "UPDATE work_tickets SET status=?, updated_at=? WHERE id=?",
            (STATUS_OPEN, _now(), ticket_id),
        )
        _add_event(conn, ticket_id, "resumed", agent_id, {"from": row["status"]})
        conn.commit()
        conn.close()
    return get_ticket(agent_id, ticket_id)  # type: ignore[return-value]


def bind_final_mails(
    agent_id: str,
    ticket_id: str,
    *,
    order_mail_id: str,
    invoice_mail_id: str,
) -> dict[str, Any]:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            "UPDATE work_tickets SET order_mail_id=?, invoice_mail_id=?, order_recv_self=1, "
            "invoice_recv_self=1, updated_at=? WHERE id=?",
            (order_mail_id, invoice_mail_id, _now(), ticket_id),
        )
        _add_event(
            conn,
            ticket_id,
            "final_mails_bound",
            agent_id,
            {"order_mail_id": order_mail_id, "invoice_mail_id": invoice_mail_id},
        )
        conn.commit()
        conn.close()
    return _maybe_archive(agent_id, ticket_id)


def on_mail_sent(agent_id: str, mail: dict[str, Any]) -> None:
    kind = mail.get("mail_kind")
    tid = mail.get("ticket_id")
    if not tid or kind not in ("e_order", "e_invoice"):
        return
    col = "order_recv_self" if kind == "e_order" else "invoice_recv_self"
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            f"UPDATE work_tickets SET {col}=1, updated_at=? WHERE id=?",
            (_now(), tid),
        )
        _add_event(conn, tid, f"{kind}_sent", agent_id, {"mail_id": mail.get("id")})
        conn.commit()
        conn.close()
    _maybe_archive(agent_id, tid)


def on_mail_received(agent_id: str, mail: dict[str, Any]) -> None:
    kind = mail.get("mail_kind")
    tid = mail.get("ticket_id")
    if not tid or kind not in ("e_order", "e_invoice"):
        return
    # 本方无同号工单时镜像一份，便于对端也跟踪完结
    if not get_ticket(agent_id, tid):
        now = _now()
        with lock_for(agent_id):
            conn = ensure_agent_db(agent_id)
            conn.execute(
                """
                INSERT OR IGNORE INTO work_tickets(
                  id, created_at, updated_at, title, kind, status,
                  peer_agent_id, case_id, state_json, detail_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    tid,
                    now,
                    now,
                    f"单据交换 · {mail.get('from_agent')}",
                    "document_exchange",
                    STATUS_OPEN,
                    mail.get("from_agent"),
                    None,
                    dumps({}),
                    dumps({"mirrored": True}),
                ),
            )
            _add_event(conn, tid, "mirrored", agent_id, {"from_mail": mail.get("id")})
            conn.commit()
            conn.close()

    self_col = "order_recv_self" if kind == "e_order" else "invoice_recv_self"
    # 发件方必已持有副本 → 对端也算已收妥
    peer_col = "order_recv_peer" if kind == "e_order" else "invoice_recv_peer"
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            f"UPDATE work_tickets SET {self_col}=1, {peer_col}=1, updated_at=? WHERE id=?",
            (_now(), tid),
        )
        _add_event(conn, tid, f"{kind}_received", agent_id, {"mail_id": mail.get("id")})
        conn.commit()
        conn.close()
    _maybe_archive(agent_id, tid)


def mark_peer_received(agent_id: str, ticket_id: str, mail_kind: str) -> None:
    col = "order_recv_peer" if mail_kind == "e_order" else "invoice_recv_peer"
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            f"UPDATE work_tickets SET {col}=1, updated_at=? WHERE id=?",
            (_now(), ticket_id),
        )
        _add_event(conn, ticket_id, f"{mail_kind}_peer_acked", agent_id, {})
        conn.commit()
        conn.close()
    _maybe_archive(agent_id, ticket_id)


def completion_flags(ticket: dict[str, Any]) -> dict[str, bool]:
    return {
        "order_self": bool(ticket.get("order_recv_self")),
        "order_peer": bool(ticket.get("order_recv_peer")),
        "invoice_self": bool(ticket.get("invoice_recv_self")),
        "invoice_peer": bool(ticket.get("invoice_recv_peer")),
        "complete": bool(
            ticket.get("order_recv_self")
            and ticket.get("order_recv_peer")
            and ticket.get("invoice_recv_self")
            and ticket.get("invoice_recv_peer")
        ),
    }


def _maybe_archive(agent_id: str, ticket_id: str) -> dict[str, Any]:
    """双方都收到最终电子订单 + 发票 → 完结回档。"""
    t = get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    flags = completion_flags(t)
    if not flags["complete"] or t["status"] == STATUS_CLOSED:
        return t
    now = _now()
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            "UPDATE work_tickets SET status=?, archived_at=?, updated_at=? WHERE id=?",
            (STATUS_CLOSED, now, now, ticket_id),
        )
        _add_event(conn, ticket_id, "archived", agent_id, {"reason": "双方已收妥电子订单与发票"})
        # 同步写入审计任务表（若存在）
        try:
            conn.execute(
                "INSERT OR REPLACE INTO audit_tasks(id, created_at, kind, title, status, detail_json) VALUES(?,?,?,?,?,?)",
                (
                    f"audit-{ticket_id}",
                    now,
                    "ticket_archive",
                    f"工单回档 {ticket_id}",
                    "done",
                    dumps({"ticket_id": ticket_id, "flags": flags}),
                ),
            )
        except Exception:
            pass
        conn.commit()
        conn.close()
    return get_ticket(agent_id, ticket_id)  # type: ignore[return-value]


def force_close(agent_id: str, ticket_id: str, *, reason: str = "manual") -> dict[str, Any]:
    """人工结束（仍要求尽量走邮件完结；此接口用于演示/运维）。"""
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            "UPDATE work_tickets SET status=?, archived_at=?, updated_at=? WHERE id=?",
            (STATUS_CLOSED, _now(), _now(), ticket_id),
        )
        _add_event(conn, ticket_id, "force_closed", agent_id, {"reason": reason})
        conn.commit()
        conn.close()
    return get_ticket(agent_id, ticket_id)  # type: ignore[return-value]


def audit_trail(agent_id: str, *, limit: int = 80) -> list[dict[str, Any]]:
    """回溯审计：工单事件时间线（含已回档）。"""
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        rows = conn.execute(
            """
            SELECT e.*, t.title AS ticket_title, t.status AS ticket_status
            FROM ticket_events e
            LEFT JOIN work_tickets t ON t.id=e.ticket_id
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
    out = []
    for r in rows:
        d = row_to_dict(r)
        if not d:
            continue
        if d.get("detail_json"):
            try:
                d["detail"] = json.loads(d["detail_json"])
            except Exception:
                d["detail"] = None
        out.append(d)
    return out
