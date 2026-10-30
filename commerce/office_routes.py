"""邮箱 / 工单 / 回溯审计 — 挂到任意智能体 FastAPI。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from commerce import logistics_tickets as lt
from commerce import mailbox as mb
from commerce import notify
from commerce import order_provenance as op
from commerce import order_tickets as ot
from commerce import tickets as tk
from commerce.db import ensure_agent_db


class MailSendIn(BaseModel):
    to_agent: str
    subject: str
    body: str = ""
    mail_kind: str = "notice"
    ticket_id: str | None = None
    attachment: dict[str, Any] | None = None


class MailReceiveIn(BaseModel):
    id: str | None = None
    created_at: str | None = None
    mail_kind: str = "notice"
    subject: str
    body: str = ""
    from_agent: str | None = None
    from_email: str | None = None
    to_email: str | None = None
    ticket_id: str | None = None
    attachment: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class TicketCreateIn(BaseModel):
    title: str
    kind: str = "procurement"
    peer_agent_id: str | None = None
    case_id: str | None = None
    state: dict[str, Any] | None = None
    detail: dict[str, Any] | None = None


class TicketStateIn(BaseModel):
    state: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class FinalDocsIn(BaseModel):
    to_agent: str
    order_doc: dict[str, Any]
    invoice_doc: dict[str, Any]


class MirrorOrderIn(BaseModel):
    id: str
    title: str
    kind: str = "order"
    peer_agent_id: str
    case_id: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)


class PeerAckIn(BaseModel):
    from_agent: str
    role: str = ""
    state: dict[str, Any] = Field(default_factory=dict)


class EmitDocsIn(BaseModel):
    from_agent: str
    order_doc: dict[str, Any]
    invoice_doc: dict[str, Any]


class CancelIn(BaseModel):
    reason: str = ""


class PeerCancelIn(BaseModel):
    from_agent: str
    reason: str = ""
    state: dict[str, Any] = Field(default_factory=dict)


class MirrorLogisticsIn(BaseModel):
    id: str
    title: str
    kind: str = "logistics_order"
    peer_agent_id: str
    case_id: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)


def mount_office(app, *, agent_id: str) -> None:
    ensure_agent_db(agent_id).close()
    router = APIRouter(tags=[f"office-{agent_id}"])

    # 采购侧已有 notifications 路由；供应/物流走 office 通用通知
    if not agent_id.startswith("buyer"):

        @router.get("/api/erp/notifications")
        def office_notifications(unread_only: bool = False, limit: int = 50) -> dict[str, Any]:
            items = notify.list_notifications(agent_id, unread_only=unread_only, limit=limit)
            return {"items": items, "unread": sum(1 for n in items if not n.get("read"))}

        @router.post("/api/erp/notifications/{nid}/read")
        def office_notification_read(nid: str) -> dict[str, str]:
            notify.mark_read(agent_id, nid)
            return {"status": "ok"}

    @router.get("/api/erp/mailbox")
    def mailbox_list(
        folder: str | None = None,
        unread_only: bool = False,
        ticket_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        return {
            "agent_id": agent_id,
            "email": mb.agent_email(agent_id),
            "items": mb.list_mail(
                agent_id, folder=folder, unread_only=unread_only, ticket_id=ticket_id, limit=limit
            ),
        }

    @router.get("/api/erp/mailbox/{mail_id}")
    def mailbox_get(mail_id: str) -> dict[str, Any]:
        m = mb.get_mail(agent_id, mail_id)
        if not m:
            raise HTTPException(404, "邮件不存在")
        mb.mark_read(agent_id, mail_id)
        return m

    @router.post("/api/erp/mailbox/send")
    def mailbox_send(body: MailSendIn) -> dict[str, Any]:
        return mb.send_mail(
            agent_id,
            to_agent=body.to_agent,
            subject=body.subject,
            body=body.body,
            mail_kind=body.mail_kind,
            ticket_id=body.ticket_id,
            attachment=body.attachment,
        )

    @router.post("/api/erp/mailbox/receive")
    def mailbox_receive(body: MailReceiveIn) -> dict[str, Any]:
        return mb.receive_local(agent_id, body.model_dump())

    @router.get("/api/erp/tickets")
    def tickets_list(status: str | None = None, include_archived: bool = True, limit: int = 50) -> dict[str, Any]:
        return {"items": tk.list_tickets(agent_id, status=status, include_archived=include_archived, limit=limit)}

    @router.post("/api/erp/tickets")
    def tickets_create(body: TicketCreateIn) -> dict[str, Any]:
        return tk.create_ticket(
            agent_id,
            title=body.title,
            kind=body.kind,
            peer_agent_id=body.peer_agent_id,
            case_id=body.case_id,
            state=body.state,
            detail=body.detail,
        )

    @router.get("/api/erp/tickets/{ticket_id}")
    def tickets_get(ticket_id: str) -> dict[str, Any]:
        t = tk.get_ticket(agent_id, ticket_id)
        if not t:
            raise HTTPException(404, "工单不存在")
        t["events"] = tk.list_events(agent_id, ticket_id)
        t["completion"] = tk.completion_flags(t)
        return t

    @router.post("/api/erp/tickets/{ticket_id}/suspend")
    def tickets_suspend(ticket_id: str, body: TicketStateIn | None = None) -> dict[str, Any]:
        try:
            return tk.suspend(
                agent_id,
                ticket_id,
                reason=(body.reason if body else ""),
                state=(body.state if body else None),
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/{ticket_id}/resume")
    def tickets_resume(ticket_id: str) -> dict[str, Any]:
        try:
            return tk.resume(agent_id, ticket_id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/{ticket_id}/state")
    def tickets_state(ticket_id: str, body: TicketStateIn) -> dict[str, Any]:
        return tk.save_state(agent_id, ticket_id, body.state)

    @router.post("/api/erp/tickets/{ticket_id}/send-final-docs")
    def tickets_final_docs(ticket_id: str, body: FinalDocsIn) -> dict[str, Any]:
        t = tk.get_ticket(agent_id, ticket_id)
        if not t:
            raise HTTPException(404, "工单不存在")
        if t["status"] == tk.STATUS_CLOSED:
            raise HTTPException(400, "已回档工单不可再发最终单据")
        return mb.compose_order_and_invoice(
            agent_id,
            to_agent=body.to_agent or t.get("peer_agent_id") or "",
            ticket_id=ticket_id,
            order_doc=body.order_doc,
            invoice_doc=body.invoice_doc,
        )

    @router.post("/api/erp/tickets/mirror-order")
    def tickets_mirror_order(body: MirrorOrderIn) -> dict[str, Any]:
        return ot.accept_mirrored_order(agent_id, body.model_dump())

    @router.post("/api/erp/tickets/{ticket_id}/ack-order")
    def tickets_ack_order(ticket_id: str) -> dict[str, Any]:
        # v2 共享订单 id 形如 ord-…
        if str(ticket_id).startswith("ord-"):
            from commerce_v2.gates import ack_order_gate

            try:
                return ack_order_gate(agent_id, ticket_id)
            except KeyError as e:
                raise HTTPException(404, str(e)) from e
        try:
            return ot.ack_order_generated(agent_id, ticket_id, sync_peer=True)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/{ticket_id}/ack-order-peer")
    def tickets_ack_order_peer(ticket_id: str, body: PeerAckIn) -> dict[str, Any]:
        try:
            return ot.apply_peer_ack(agent_id, ticket_id, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/{ticket_id}/emit-final-docs")
    def tickets_emit_final_docs(ticket_id: str, body: EmitDocsIn) -> dict[str, Any]:
        try:
            return ot.emit_final_docs_as_peer(agent_id, ticket_id, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/{ticket_id}/cancel-order")
    def tickets_cancel_order(ticket_id: str, body: CancelIn) -> dict[str, Any]:
        try:
            return ot.cancel_order(agent_id, ticket_id, body.reason, sync_peer=True)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/{ticket_id}/cancel-order-peer")
    def tickets_cancel_order_peer(ticket_id: str, body: PeerCancelIn) -> dict[str, Any]:
        try:
            return ot.apply_peer_cancel(agent_id, ticket_id, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/mirror-logistics")
    def tickets_mirror_logistics(body: MirrorLogisticsIn) -> dict[str, Any]:
        return lt.accept_mirrored_logistics(agent_id, body.model_dump())

    @router.post("/api/erp/tickets/{ticket_id}/ack-logistics")
    def tickets_ack_logistics(ticket_id: str) -> dict[str, Any]:
        if str(ticket_id).startswith("log-"):
            from commerce_v2.gates import ack_logistics_gate

            try:
                return ack_logistics_gate(agent_id, ticket_id)
            except KeyError as e:
                raise HTTPException(404, str(e)) from e
        try:
            return lt.ack_logistics(agent_id, ticket_id, sync_peer=True)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/{ticket_id}/ack-logistics-peer")
    def tickets_ack_logistics_peer(ticket_id: str, body: PeerAckIn) -> dict[str, Any]:
        try:
            return lt.apply_peer_logistics_ack(agent_id, ticket_id, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/{ticket_id}/cancel-logistics")
    def tickets_cancel_logistics(ticket_id: str, body: CancelIn) -> dict[str, Any]:
        try:
            return lt.cancel_logistics(agent_id, ticket_id, body.reason, sync_peer=True)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.post("/api/erp/tickets/{ticket_id}/cancel-logistics-peer")
    def tickets_cancel_logistics_peer(ticket_id: str, body: PeerCancelIn) -> dict[str, Any]:
        try:
            return lt.apply_peer_logistics_cancel(agent_id, ticket_id, body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @router.get("/api/erp/office-audit")
    def office_audit(limit: int = 80) -> dict[str, Any]:
        return {"items": tk.audit_trail(agent_id, limit=limit)}

    @router.get("/api/erp/order-provenance")
    def order_provenance(case_id: str | None = None, ticket_id: str | None = None) -> dict[str, Any]:
        if not case_id and not ticket_id:
            raise HTTPException(400, "需要 case_id 或 ticket_id")
        try:
            return op.build_provenance(agent_id, case_id=case_id, ticket_id=ticket_id)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, str(e)) from e

    @router.get("/api/erp/order-provenance/list")
    def order_provenance_list(limit: int = 30) -> dict[str, Any]:
        """可回溯的订单工单列表（供审计页入口）。"""
        items = []
        for t in tk.list_tickets(agent_id, limit=limit):
            if t.get("kind") != "order" and not t.get("case_id"):
                continue
            items.append(
                {
                    "ticket_id": t.get("id"),
                    "case_id": t.get("case_id"),
                    "title": t.get("title"),
                    "status": t.get("status"),
                    "peer_agent_id": t.get("peer_agent_id"),
                    "updated_at": t.get("updated_at"),
                    "order_status": (t.get("state") or {}).get("order_status"),
                }
            )
        return {"items": items}

    app.include_router(router)
