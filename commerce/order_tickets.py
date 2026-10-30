"""订单草案 → 双边工单 → 双方确认「订单已生成」→ 互发电子订单/发票 → 工单回档。"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from commerce import mailbox as mb
from commerce import notify
from commerce import tickets as tk
from commerce.db import dumps
from commerce.mailbox import AGENT_API_BASE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _buyer_id() -> str:
    return (os.getenv("BUYER_AGENT_ID") or "buyer-a").strip()


def _http_post(agent_id: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base = (AGENT_API_BASE.get(agent_id) or "").rstrip("/")
    if not base:
        return {"ok": False, "error": f"no api base for {agent_id}"}
    url = f"{base}{path}"
    verify = os.getenv("UI_HTTPX_VERIFY", "0") not in ("0", "false", "False")
    try:
        with httpx.Client(timeout=25.0, verify=verify) as client:
            r = client.post(url, json=payload)
            if r.status_code >= 400:
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
            return {"ok": True, "data": r.json() if r.content else {}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _ticket_id_for_case(case_id: str, *, supplier: str = "", sku: str = "") -> str:
    """同一采购案拆单时，按供方(+SKU)区分工单，避免第二单被 INSERT OR IGNORE 吞掉。"""
    safe = "".join(c for c in case_id if c.isalnum() or c in "-_")[-12:]
    parts = [f"tk-ord-{safe}"]
    if supplier:
        parts.append("".join(c for c in supplier if c.isalnum() or c in "-_")[-10:] or "sup")
    if sku:
        parts.append("".join(c for c in str(sku) if c.isalnum() or c in "-_")[-12:] or "sku")
    return "-".join(parts)


def _order_summary(case: dict[str, Any]) -> dict[str, Any]:
    draft = (case.get("order_draft") or {}).get("payload") or case.get("order_draft") or {}
    if not isinstance(draft, dict):
        draft = {}
    brief = case.get("brief") or {}
    # 组合案 brief 仍是多物料全文；工单标题/摘要必须以本单草案为准（拆单后只含该供方承接行）
    product_name = draft.get("product_name") or brief.get("product_name")
    quantity = draft.get("quantity") if draft.get("quantity") is not None else brief.get("quantity")
    sku = draft.get("sku")
    return {
        "case_id": case.get("case_id"),
        "supplier_agent_id": case.get("selected_supplier") or draft.get("supplier_agent_id"),
        "product_name": product_name,
        "sku": sku,
        "quantity": quantity,
        "unit_price": draft.get("unit_price"),
        "goods_total": draft.get("goods_total"),
        "freight": draft.get("freight_amount") or draft.get("shipping_cost"),
        "currency": draft.get("currency") or "CNY",
        "order_draft": draft,
    }


def _upsert_local_ticket(
    agent_id: str,
    *,
    ticket_id: str,
    title: str,
    peer_agent_id: str,
    case_id: str,
    state: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, Any]:
    existing = tk.get_ticket(agent_id, ticket_id)
    if existing:
        return existing
    # 直接插入固定 id（create_ticket 会随机 id）
    from commerce.db import ensure_agent_db, lock_for

    now = _now()
    with lock_for(agent_id):
        conn = ensure_agent_db(agent_id)
        conn.execute(
            """
            INSERT OR IGNORE INTO work_tickets(
              id, created_at, updated_at, title, kind, status,
              peer_agent_id, peer_email, case_id, state_json, detail_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ticket_id,
                now,
                now,
                title,
                "order",
                tk.STATUS_OPEN,
                peer_agent_id,
                mb.agent_email(peer_agent_id),
                case_id,
                dumps(state),
                dumps(detail),
            ),
        )
        conn.execute(
            "INSERT INTO ticket_events(id, ticket_id, created_at, event, actor, detail_json) VALUES(?,?,?,?,?,?)",
            (f"tev-{uuid4().hex[:10]}", ticket_id, now, "order_ticket_created", agent_id, dumps({"case_id": case_id})),
        )
        conn.commit()
        conn.close()
    return tk.get_ticket(agent_id, ticket_id) or {"id": ticket_id}


def spawn_order_ticket_from_case(case: dict[str, Any], *, buyer_agent_id: str | None = None) -> dict[str, Any]:
    """订单草案生成后：买方/卖方各建同号工单 + 通知。"""
    buyer = buyer_agent_id or _buyer_id()
    supplier = str(case.get("selected_supplier") or "")
    if not supplier:
        return {"ok": False, "error": "无选定供应商"}
    case_id = str(case.get("case_id") or "")
    summary = _order_summary(case)
    tid = _ticket_id_for_case(
        case_id,
        supplier=supplier,
        sku=str(summary.get("sku") or ""),
    )
    # 异构视图：采购看「采购订单」，供应看「销售订单」——品名取草案本行，不含组合案其它物料
    line_label = str(summary.get("product_name") or summary.get("sku") or case_id)
    qty_label = summary.get("quantity") if summary.get("quantity") is not None else "?"
    title_buyer = f"采购订单 · {line_label} × {qty_label} · 供方 {supplier}"
    title_supplier = (
        f"销售订单 · {line_label} × {qty_label} · "
        f"买方 {buyer} · 货款 {summary.get('goods_total') or '—'}"
    )
    state_buyer = {
        "phase": "await_order_ack",
        "order_status": "pending_ack",
        "buyer_order_ack": False,
        "supplier_order_ack": False,
        "view": "buyer",
        "summary": summary,
    }
    state_supplier = {
        **state_buyer,
        "view": "supplier",
        "summary": {
            **summary,
            "buyer_agent_id": buyer,
            "sell_side_note": "待双方确认后生效，再生效物流询价",
        },
    }
    detail = {"case_id": case_id, "spawned_at": _now()}

    buyer_t = _upsert_local_ticket(
        buyer,
        ticket_id=tid,
        title=title_buyer,
        peer_agent_id=supplier,
        case_id=case_id,
        state=state_buyer,
        detail=detail,
    )
    notify.push(
        buyer,
        title="新订单已生成",
        body=f"采购案 {case_id} 已生成订单草案，请前往「工单待办」确认或取消。",
        level="info",
        payload={"ticket_id": tid, "case_id": case_id, "kind": "order_spawned"},
    )

    mirror = {
        "id": tid,
        "title": title_supplier,
        "kind": "order",
        "peer_agent_id": buyer,
        "case_id": case_id,
        "state": state_supplier,
        "detail": {**detail, "mirrored_from": buyer},
    }
    remote = _http_post(supplier, "/api/erp/tickets/mirror-order", mirror)
    if not remote.get("ok"):
        # 同机兜底
        try:
            _upsert_local_ticket(
                supplier,
                ticket_id=tid,
                title=title_supplier,
                peer_agent_id=buyer,
                case_id=case_id,
                state=state_supplier,
                detail=mirror["detail"],
            )
            notify.push(
                supplier,
                title="新销售订单待确认",
                body=f"来自 {buyer} 的订单（案 {case_id}），请在「工单待办」确认或取消。",
                level="info",
                payload={"ticket_id": tid, "case_id": case_id, "kind": "order_spawned"},
            )
            remote = {"ok": True, "local_fallback": True}
        except Exception as exc:  # noqa: BLE001
            remote = {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "ticket_id": tid,
        "buyer_ticket": buyer_t,
        "supplier_mirror": remote,
        "case_id": case_id,
    }


def accept_mirrored_order(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    tid = str(payload.get("id") or "")
    if not tid:
        raise ValueError("missing ticket id")
    t = _upsert_local_ticket(
        agent_id,
        ticket_id=tid,
        title=str(payload.get("title") or "订单工单"),
        peer_agent_id=str(payload.get("peer_agent_id") or ""),
        case_id=str(payload.get("case_id") or ""),
        state=dict(payload.get("state") or {}),
        detail=dict(payload.get("detail") or {}),
    )
    notify.push(
        agent_id,
        title="新订单已生成",
        body=f"对端订单工单 {tid} 已同步，请确认「订单已生成」。",
        level="info",
        payload={"ticket_id": tid, "case_id": payload.get("case_id"), "kind": "order_spawned"},
    )
    return t


def _role_of(agent_id: str) -> str:
    if agent_id.startswith("buyer"):
        return "buyer"
    if agent_id.startswith("supplier"):
        return "supplier"
    return "other"


def ack_order_generated(agent_id: str, ticket_id: str, *, sync_peer: bool = True) -> dict[str, Any]:
    """本方确认订单；双方确认后订单生效 → 互发单据；由订单发起方（采购）联系物流。"""
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    if t.get("status") == tk.STATUS_CLOSED:
        return t
    if t.get("kind") != "order":
        raise ValueError("非订单工单")
    state = dict(t.get("state") or {})
    if state.get("cancelled"):
        raise ValueError("订单已取消，无法确认")

    role = _role_of(agent_id)
    if role == "buyer":
        state["buyer_order_ack"] = True
    elif role == "supplier":
        state["supplier_order_ack"] = True
    else:
        raise ValueError("当前角色无法确认订单")

    both = bool(state.get("buyer_order_ack") and state.get("supplier_order_ack"))
    state["order_status"] = "both_acked" if both else ("buyer_acked" if state.get("buyer_order_ack") else "supplier_acked")
    state["phase"] = "effective" if both else "await_order_ack"
    if both:
        state["order_effective"] = True
        state["effective_at"] = _now()
    t = tk.save_state(agent_id, ticket_id, state, actor=agent_id)

    peer = str(t.get("peer_agent_id") or "")
    if sync_peer and peer:
        _http_post(
            peer,
            f"/api/erp/tickets/{ticket_id}/ack-order-peer",
            {"from_agent": agent_id, "role": role, "state": state},
        )

    result: dict[str, Any]
    if both and not state.get("docs_sent"):
        result = _dispatch_final_docs(agent_id, ticket_id)
    else:
        result = tk.get_ticket(agent_id, ticket_id) or t
    if both:
        _maybe_start_logistics(agent_id, ticket_id)
    return result


def apply_peer_ack(agent_id: str, ticket_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    incoming = dict(payload.get("state") or {})
    state = dict(t.get("state") or {})
    if state.get("cancelled") or incoming.get("cancelled"):
        return t
    state["buyer_order_ack"] = bool(incoming.get("buyer_order_ack") or state.get("buyer_order_ack"))
    state["supplier_order_ack"] = bool(incoming.get("supplier_order_ack") or state.get("supplier_order_ack"))
    both = bool(state.get("buyer_order_ack") and state.get("supplier_order_ack"))
    state["order_status"] = "both_acked" if both else state.get("order_status") or "pending_ack"
    state["phase"] = "effective" if both else "await_order_ack"
    if both:
        state["order_effective"] = True
        state["effective_at"] = _now()
    tk.save_state(agent_id, ticket_id, state, actor=payload.get("from_agent"))
    result: dict[str, Any]
    if both and not state.get("docs_sent"):
        result = _dispatch_final_docs(agent_id, ticket_id)
    else:
        result = tk.get_ticket(agent_id, ticket_id)  # type: ignore[return-value]
    if both:
        _maybe_start_logistics(agent_id, ticket_id)
    return result


def cancel_order(agent_id: str, ticket_id: str, reason: str, *, sync_peer: bool = True) -> dict[str, Any]:
    """任一方取消订单（须理由）；同步对端并回档，不发电子单据。"""
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("取消订单须填写理由")
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    if t.get("kind") != "order":
        raise ValueError("非订单工单")
    if t.get("status") == tk.STATUS_CLOSED:
        return t
    state = dict(t.get("state") or {})
    if state.get("order_effective") and state.get("docs_sent"):
        raise ValueError("订单已生效并出单，不能再取消")
    state["cancelled"] = True
    state["cancel_reason"] = reason
    state["cancelled_by"] = agent_id
    state["cancelled_at"] = _now()
    state["phase"] = "cancelled"
    state["order_status"] = "cancelled"
    tk.save_state(agent_id, ticket_id, state, actor=agent_id)
    tk.force_close(agent_id, ticket_id, reason=f"cancel: {reason}")
    peer = str(t.get("peer_agent_id") or "")
    if sync_peer and peer:
        _http_post(
            peer,
            f"/api/erp/tickets/{ticket_id}/cancel-order-peer",
            {"from_agent": agent_id, "reason": reason, "state": state},
        )
    notify.push(
        agent_id,
        title="订单已取消",
        body=f"工单 {ticket_id} 已取消：{reason}",
        level="warning",
        payload={"ticket_id": ticket_id, "kind": "order_cancelled"},
    )
    return tk.get_ticket(agent_id, ticket_id) or t


def apply_peer_cancel(agent_id: str, ticket_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    state = dict(payload.get("state") or t.get("state") or {})
    state["cancelled"] = True
    state["cancel_reason"] = payload.get("reason") or state.get("cancel_reason")
    state["phase"] = "cancelled"
    state["order_status"] = "cancelled"
    tk.save_state(agent_id, ticket_id, state, actor=payload.get("from_agent"))
    if t.get("status") != tk.STATUS_CLOSED:
        tk.force_close(agent_id, ticket_id, reason=f"peer_cancel: {payload.get('reason')}")
    notify.push(
        agent_id,
        title="对端取消了订单",
        body=f"{payload.get('from_agent')}：{payload.get('reason')}",
        level="warning",
        payload={"ticket_id": ticket_id, "kind": "order_cancelled"},
    )
    return tk.get_ticket(agent_id, ticket_id) or t


def _maybe_start_logistics(agent_id: str, ticket_id: str) -> None:
    """订单生效后：不自动拉物流单，仅提示采购去与物流智能体对话询价/下单。"""
    if not agent_id.startswith("buyer"):
        return
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        return
    state = dict(t.get("state") or {})
    if state.get("logistics_prompted") or state.get("cancelled"):
        return
    summary = dict(state.get("summary") or {}) if isinstance(state.get("summary"), dict) else {}
    vol = summary.get("volume_m3") or (summary.get("product") or {}).get("volume_m3")
    origin = summary.get("origin_city") or summary.get("ship_from_city") or "供应发货地"
    dest = "保定"
    try:
        from commerce.merchant import buyer_destination, profile as merchant_profile

        dest = str((buyer_destination(agent_id) or {}).get("city") or merchant_profile(agent_id).get("city") or dest)
        peer = str(t.get("peer_agent_id") or "")
        if peer.startswith("supplier") and not summary.get("origin_city"):
            origin = str(
                merchant_profile(peer).get("ship_from_city")
                or merchant_profile(peer).get("city")
                or origin
            )
    except Exception:  # noqa: BLE001
        pass

    state["logistics_prompted"] = True
    state["logistics_prompted_at"] = _now()
    state["logistics_phase"] = "await_buyer_dialog"
    # 兼容旧字段：未真正 spawn
    state["logistics_spawned"] = False
    tk.save_state(agent_id, ticket_id, state, actor=agent_id)

    hint = (
        f"采购订单已生效。请下一步与「物流」智能体对话下承运单："
        f"说明总体积{vol if vol is not None else '（见订单规格）'}、"
        f"起点{origin}→{dest}，先询价再正式下单；双方人工确认后物流单生效。"
    )
    notify.push(
        agent_id,
        title="订单已生效 · 请联系物流下单",
        body=hint,
        level="info",
        payload={
            "ticket_id": ticket_id,
            "kind": "logistics_prompt",
            "case_id": t.get("case_id"),
            "suggested_utterance": (
                f"我打算下一个物流单，总体积为{vol if vol is not None else '按订单规格'}，"
                f"起点{origin}到{dest}，请给我报价"
            ),
        },
    )
    case_id = str(t.get("case_id") or summary.get("case_id") or "")
    if case_id:
        try:
            from commerce import procurement_case as pc
            from commerce.choice_actions import post_order_effective_logistics_choices

            widget = post_order_effective_logistics_choices(
                case_id=case_id,
                order_ticket_id=ticket_id,
                origin_city=str(origin),
                dest_city=str(dest),
                volume_m3=vol,
            )
            pc.update_case(case_id, pending_choices=widget)
        except Exception:  # noqa: BLE001
            pass


def _dispatch_final_docs(agent_id: str, ticket_id: str) -> dict[str, Any]:
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    state = dict(t.get("state") or {})
    if state.get("docs_sent"):
        return t
    peer = str(t.get("peer_agent_id") or "")
    summary = (state.get("summary") or {}) if isinstance(state.get("summary"), dict) else {}
    order_no = f"EO-{ticket_id[-8:].upper()}"
    inv_no = f"EI-{ticket_id[-8:].upper()}"
    order_doc = {
        "order_no": order_no,
        "summary": f"电子订单 {order_no} · {summary.get('product_name')} × {summary.get('quantity')}",
        "case_id": t.get("case_id") or summary.get("case_id"),
        "ticket_id": ticket_id,
        **{k: summary[k] for k in ("product_name", "quantity", "unit_price", "goods_total", "freight", "currency") if k in summary},
    }
    invoice_doc = {
        "invoice_no": inv_no,
        "summary": f"电子发票 {inv_no} · 对应订单 {order_no}",
        "order_no": order_no,
        "amount": summary.get("goods_total"),
        "currency": summary.get("currency") or "CNY",
        "ticket_id": ticket_id,
    }
    # 本方作为发件方向对端发送；对端收件箱签收后推进完结标志
    docs = mb.compose_order_and_invoice(
        agent_id,
        to_agent=peer,
        ticket_id=ticket_id,
        order_doc=order_doc,
        invoice_doc=invoice_doc,
    )
    state["docs_sent"] = True
    state["docs_sent_at"] = _now()
    state["phase"] = "docs_sent"
    state["order_status"] = "docs_sent"
    tk.save_state(agent_id, ticket_id, state, actor=agent_id)
    notify.push(
        agent_id,
        title="电子订单/发票已发出",
        body=f"工单 {ticket_id} 已向 {peer} 发送电子订单与发票；双方收妥后工单回档。",
        level="info",
        payload={"ticket_id": ticket_id, "kind": "docs_sent"},
    )
    # 提醒对端也走一遍发件（或仅依赖本方发出的收件）。为满足「双方邮箱都有」，
    # 再让对端镜像发一封回执副本到本方（若对端在线）。
    _http_post(
        peer,
        f"/api/erp/tickets/{ticket_id}/emit-final-docs",
        {"order_doc": order_doc, "invoice_doc": invoice_doc, "from_agent": agent_id},
    )
    return {"ticket": tk.get_ticket(agent_id, ticket_id), "docs": docs}


def emit_final_docs_as_peer(agent_id: str, ticket_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """对端收到「请发最终单据」请求：向发起方邮箱回发同样电子订单/发票。"""
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    peer = str(payload.get("from_agent") or t.get("peer_agent_id") or "")
    order_doc = dict(payload.get("order_doc") or {})
    invoice_doc = dict(payload.get("invoice_doc") or {})
    docs = mb.compose_order_and_invoice(
        agent_id,
        to_agent=peer,
        ticket_id=ticket_id,
        order_doc=order_doc,
        invoice_doc=invoice_doc,
    )
    state = dict(t.get("state") or {})
    state["docs_sent"] = True
    state["docs_sent_at"] = _now()
    state["phase"] = "docs_sent"
    tk.save_state(agent_id, ticket_id, state, actor=agent_id)
    return {"ok": True, "docs": docs, "ticket": tk.get_ticket(agent_id, ticket_id)}
