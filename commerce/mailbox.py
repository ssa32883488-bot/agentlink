"""站内电子邮箱：电子订单 / 发票首发与签收。"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from commerce.db import dumps, ensure_agent_db, lock_for, row_to_dict
from commerce.merchant import profile as merchant_profile

def _rpc_to_api(env_key: str, default_rpc: str) -> str:
    return (os.getenv(env_key) or default_rpc).replace("/rpc", "").rstrip("/")


# agent_id → HTTP API base（非 /rpc）；跨云投递电子邮
AGENT_API_BASE: dict[str, str] = {
    "buyer-a": os.getenv("BUYER_A_API_BASE", "https://ashui.online:8010"),
    "buyer-b": os.getenv("BUYER_B_API_BASE", "https://ashui.online:8012"),
    "supplier-a": os.getenv("SUPPLIER_A_API_BASE")
    or _rpc_to_api("SUPPLIER_A_RPC_URL", "https://39.105.20.113:8011/rpc"),
    "supplier-b": os.getenv("SUPPLIER_B_API_BASE")
    or _rpc_to_api("SUPPLIER_B_RPC_URL", "https://39.105.20.113:8013/rpc"),
    "supplier-c": os.getenv("SUPPLIER_C_API_BASE")
    or _rpc_to_api("SUPPLIER_C_RPC_URL", "https://39.105.20.113:8014/rpc"),
    "logistics": os.getenv("LOGISTICS_API_BASE", "https://ashui.online:8015"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def agent_email(agent_id: str) -> str:
    p = merchant_profile(agent_id)
    if p.get("email"):
        return str(p["email"])
    org = str(p.get("organization") or agent_id).replace(" ", "")
    return f"{agent_id}@{org}.agentlink.local"


def list_mail(
    agent_id: str,
    *,
    folder: str | None = None,
    unread_only: bool = False,
    ticket_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ensure_agent_db(agent_id).close()
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        sql = "SELECT * FROM mailbox WHERE 1=1"
        args: list[Any] = []
        if folder:
            sql += " AND folder=?"
            args.append(folder)
        if unread_only:
            sql += " AND read=0"
        if ticket_id:
            sql += " AND ticket_id=?"
            args.append(ticket_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        rows = [row_to_dict(r) for r in conn.execute(sql, args).fetchall()]
        conn.close()
    for r in rows:
        if r and r.get("attachment_json"):
            import json

            try:
                r["attachment"] = json.loads(r["attachment_json"])
            except Exception:
                r["attachment"] = None
        if r and r.get("meta_json"):
            import json

            try:
                r["meta"] = json.loads(r["meta_json"])
            except Exception:
                r["meta"] = None
    return [r for r in rows if r]


def get_mail(agent_id: str, mail_id: str) -> dict[str, Any] | None:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        row = row_to_dict(conn.execute("SELECT * FROM mailbox WHERE id=?", (mail_id,)).fetchone())
        conn.close()
    if not row:
        return None
    import json

    for key, out in (("attachment_json", "attachment"), ("meta_json", "meta")):
        if row.get(key):
            try:
                row[out] = json.loads(row[key])
            except Exception:
                row[out] = None
    return row


def mark_read(agent_id: str, mail_id: str) -> None:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute("UPDATE mailbox SET read=1 WHERE id=?", (mail_id,))
        conn.commit()
        conn.close()


def _insert_mail(agent_id: str, row: dict[str, Any]) -> None:
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            """
            INSERT OR REPLACE INTO mailbox(
              id, created_at, direction, folder, mail_kind, subject, body,
              from_agent, from_email, to_agent, to_email, ticket_id,
              attachment_json, read, acked, meta_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["id"],
                row["created_at"],
                row["direction"],
                row["folder"],
                row["mail_kind"],
                row["subject"],
                row["body"],
                row.get("from_agent"),
                row.get("from_email"),
                row.get("to_agent"),
                row.get("to_email"),
                row.get("ticket_id"),
                dumps(row.get("attachment")) if row.get("attachment") is not None else None,
                int(row.get("read") or 0),
                int(row.get("acked") or 0),
                dumps(row.get("meta")) if row.get("meta") is not None else None,
            ),
        )
        conn.commit()
        conn.close()


def receive_local(agent_id: str, mail: dict[str, Any]) -> dict[str, Any]:
    """对端投递到本方收件箱。"""
    mid = mail.get("id") or f"mail-{uuid4().hex[:12]}"
    row = {
        "id": mid,
        "created_at": mail.get("created_at") or _now(),
        "direction": "inbound",
        "folder": "inbox",
        "mail_kind": mail.get("mail_kind") or "notice",
        "subject": mail.get("subject") or "(无主题)",
        "body": mail.get("body") or "",
        "from_agent": mail.get("from_agent"),
        "from_email": mail.get("from_email"),
        "to_agent": agent_id,
        "to_email": mail.get("to_email") or agent_email(agent_id),
        "ticket_id": mail.get("ticket_id"),
        "attachment": mail.get("attachment"),
        "read": 0,
        "acked": 0,
        "meta": mail.get("meta"),
    }
    _insert_mail(agent_id, row)
    # 签收电子订单/发票 → 推进工单完结条件
    if row["mail_kind"] in ("e_order", "e_invoice") and row.get("ticket_id"):
        from commerce import tickets as tk

        tk.on_mail_received(agent_id, row)
    return get_mail(agent_id, mid) or row


def _deliver_remote(to_agent: str, mail: dict[str, Any]) -> dict[str, Any]:
    base = (AGENT_API_BASE.get(to_agent) or "").rstrip("/")
    if not base:
        return {"ok": False, "error": f"无 API base: {to_agent}"}
    url = f"{base}/api/erp/mailbox/receive"
    verify = os.getenv("UI_HTTPX_VERIFY", "0") not in ("0", "false", "False")
    err: str | None = None
    try:
        with httpx.Client(timeout=20.0, verify=verify) as client:
            r = client.post(url, json=mail)
            if r.status_code >= 400:
                err = f"HTTP {r.status_code}: {r.text[:200]}"
            else:
                return {"ok": True, "remote": r.json() if r.content else {}}
    except Exception as exc:  # noqa: BLE001
        err = str(exc)

    # 本域同机（127.0.0.1 / localhost）失败时直写对端库；跨云不直写以免污染本机库
    localish = ("127.0.0.1" in base) or ("localhost" in base) or os.getenv("OFFICE_LOCAL_FALLBACK") == "1"
    if localish:
        try:
            receive_local(to_agent, mail)
            return {"ok": True, "local_fallback": True, "remote_error": err}
        except Exception as exc2:  # noqa: BLE001
            return {"ok": False, "error": f"{err}; fallback: {exc2}"}
    return {"ok": False, "error": err or "deliver failed"}


def send_mail(
    agent_id: str,
    *,
    to_agent: str,
    subject: str,
    body: str,
    mail_kind: str = "notice",
    ticket_id: str | None = None,
    attachment: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mid = f"mail-{uuid4().hex[:12]}"
    created = _now()
    from_email = agent_email(agent_id)
    to_email = agent_email(to_agent)
    out = {
        "id": mid,
        "created_at": created,
        "direction": "outbound",
        "folder": "sent",
        "mail_kind": mail_kind,
        "subject": subject,
        "body": body,
        "from_agent": agent_id,
        "from_email": from_email,
        "to_agent": to_agent,
        "to_email": to_email,
        "ticket_id": ticket_id,
        "attachment": attachment,
        "read": 1,
        "acked": 0,
        "meta": meta or {},
    }
    _insert_mail(agent_id, out)
    # 发件方也视为「已持有」最终单据副本（用于双方收妥判定中的 self）
    if mail_kind in ("e_order", "e_invoice") and ticket_id:
        from commerce import tickets as tk

        tk.on_mail_sent(agent_id, out)

    payload = {**out, "folder": "inbox", "direction": "inbound", "read": 0}
    delivery = _deliver_remote(to_agent, payload)
    if delivery.get("ok") and ticket_id and mail_kind in ("e_order", "e_invoice"):
        from commerce import tickets as tk

        tk.mark_peer_received(agent_id, ticket_id, mail_kind)
    saved = get_mail(agent_id, mid) or out
    saved["delivery"] = delivery
    return saved


def compose_order_and_invoice(
    agent_id: str,
    *,
    to_agent: str,
    ticket_id: str,
    order_doc: dict[str, Any],
    invoice_doc: dict[str, Any],
) -> dict[str, Any]:
    """首发写好的电子订单 + 发票（两封邮件）。"""
    order_mail = send_mail(
        agent_id,
        to_agent=to_agent,
        subject=f"【电子订单】{order_doc.get('order_no') or ticket_id}",
        body=order_doc.get("summary")
        or f"请查收电子订单。工单 {ticket_id}。\n\n{dumps(order_doc)}",
        mail_kind="e_order",
        ticket_id=ticket_id,
        attachment={"type": "electronic_order", "doc": order_doc},
        meta={"doc_role": "final_order"},
    )
    invoice_mail = send_mail(
        agent_id,
        to_agent=to_agent,
        subject=f"【电子发票】{invoice_doc.get('invoice_no') or ticket_id}",
        body=invoice_doc.get("summary")
        or f"请查收电子发票。工单 {ticket_id}。\n\n{dumps(invoice_doc)}",
        mail_kind="e_invoice",
        ticket_id=ticket_id,
        attachment={"type": "electronic_invoice", "doc": invoice_doc},
        meta={"doc_role": "final_invoice"},
    )
    from commerce import tickets as tk

    tk.bind_final_mails(agent_id, ticket_id, order_mail_id=order_mail["id"], invoice_mail_id=invoice_mail["id"])
    return {"order_mail": order_mail, "invoice_mail": invoice_mail}
