"""采购（订单发起方）↔物流：物流订单工单双边确认；生效后回写运费报价。

供应侧不再主动联系物流拉承运工单。
"""
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


def _http_post(agent_id: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base = (AGENT_API_BASE.get(agent_id) or "").rstrip("/")
    if not base:
        return {"ok": False, "error": f"no api base for {agent_id}"}
    verify = os.getenv("UI_HTTPX_VERIFY", "0") not in ("0", "false", "False")
    try:
        with httpx.Client(timeout=40.0, verify=verify) as client:
            r = client.post(f"{base}{path}", json=payload)
            if r.status_code >= 400:
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
            return {"ok": True, "data": r.json() if r.content else {}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _ticket_id(order_ticket_id: str) -> str:
    safe = "".join(c for c in order_ticket_id if c.isalnum() or c in "-_")[-14:]
    return f"tk-log-{safe}"


def _upsert(
    agent_id: str,
    *,
    ticket_id: str,
    title: str,
    peer_agent_id: str,
    case_id: str | None,
    state: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, Any]:
    existing = tk.get_ticket(agent_id, ticket_id)
    if existing:
        return existing
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
                "logistics_order",
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
            (f"tev-{uuid4().hex[:10]}", ticket_id, now, "logistics_ticket_created", agent_id, dumps(detail)),
        )
        conn.commit()
        conn.close()
    return tk.get_ticket(agent_id, ticket_id) or {"id": ticket_id}


def _role(agent_id: str) -> str:
    if agent_id.startswith("buyer"):
        return "buyer"
    if agent_id.startswith("supplier"):
        return "supplier"
    if agent_id == "logistics" or agent_id.startswith("logistics"):
        return "logistics"
    return "other"


def _shipper_acked(state: dict[str, Any]) -> bool:
    """采购或历史供应侧任一方确认，均视为托运方已确认（兼容旧工单）。"""
    return bool(state.get("buyer_logistics_ack") or state.get("supplier_logistics_ack"))


async def quote_and_spawn_from_order(
    initiator_agent_id: str,
    *,
    order_ticket: dict[str, Any],
) -> dict[str, Any]:
    """订单生效后由采购（发起方）联系物流：询运 → 生成采购↔物流双边工单。

    兼容旧调用：若误传 supplier-*，自动改走订单上的采购方，避免供应再询运。
    """
    from agents.supplier_common.freight import attach_freight
    from agentlink_runtime.graph_base import AgentState

    st = dict(order_ticket.get("state") or {})
    summary = dict(st.get("summary") or {})
    case_id = str(order_ticket.get("case_id") or summary.get("case_id") or "")
    order_tid = str(order_ticket.get("id") or "")
    tid = _ticket_id(order_tid or case_id or uuid4().hex[:8])

    # 解析采购 / 供应
    peer = str(order_ticket.get("peer_agent_id") or "")
    if initiator_agent_id.startswith("buyer"):
        buyer_agent_id = initiator_agent_id
        supplier_agent_id = peer if peer.startswith("supplier") else str(
            summary.get("supplier_agent_id") or st.get("supplier_agent_id") or ""
        )
    elif initiator_agent_id.startswith("supplier"):
        # 旧入口：不再由供应联系物流，改为采购发起
        supplier_agent_id = initiator_agent_id
        buyer_agent_id = peer if peer.startswith("buyer") else str(
            summary.get("buyer_agent_id") or st.get("buyer_agent_id") or "buyer-a"
        )
        initiator_agent_id = buyer_agent_id
    else:
        buyer_agent_id = "buyer-a"
        supplier_agent_id = peer if peer.startswith("supplier") else ""
        initiator_agent_id = buyer_agent_id

    if not supplier_agent_id.startswith("supplier"):
        supplier_agent_id = str(summary.get("supplier_agent_id") or "supplier-a")

    dest = summary.get("destination") if isinstance(summary.get("destination"), dict) else {}
    rfq_payload = {
        "need_freight": True,
        "quantity": summary.get("quantity") or 1,
        "sku": summary.get("sku") or summary.get("product_sku"),
        "product_name": summary.get("product_name"),
        "destination": dest
        or {"city": summary.get("ship_to_city"), "postal_code": summary.get("postal_code") or "071000"},
        "postal_code": summary.get("postal_code") or dest.get("postal_code") or "071000",
        "purchase_request_id": case_id or order_tid,
    }
    quote_payload = {
        "product": {"name": summary.get("product_name"), "quantity": summary.get("quantity")},
        "goods_total": summary.get("goods_total"),
        "currency": summary.get("currency") or "CNY",
    }

    buyer_aic = (
        os.getenv("BUYER_A_AIC")
        if buyer_agent_id == "buyer-a"
        else (os.getenv("BUYER_B_AIC") or os.getenv("BUYER_A_AIC"))
    ) or os.getenv("BUYER_A_AIC") or ""
    state_aip: AgentState = {
        "agent_id": buyer_agent_id,
        "business_id": case_id or order_tid,
        "aic": buyer_aic,
    }
    # 发货地按供应侧城市；AIP Leader 身份用采购
    policy = {
        "ship_from_city": summary.get("origin_city") or summary.get("ship_from_city"),
    }
    if not policy.get("ship_from_city"):
        try:
            from commerce.merchant import profile as merchant_profile

            policy["ship_from_city"] = merchant_profile(supplier_agent_id).get("ship_from_city") or merchant_profile(
                supplier_agent_id
            ).get("city")
        except Exception:  # noqa: BLE001
            pass

    quoted = await attach_freight(
        quote_payload,
        rfq_payload=rfq_payload,
        state=state_aip,
        policy=policy,
    )
    freight = quoted.get("freight") if isinstance(quoted.get("freight"), dict) else {}
    meta = quoted.get("logistics_meta") if isinstance(quoted.get("logistics_meta"), dict) else {}

    logistics_id = "logistics"
    title_buyer = (
        f"物流订单 · {summary.get('product_name') or case_id} · "
        f"运费 {freight.get('amount', '—')} · ETA {freight.get('eta_days', '—')}天"
    )
    title_log = (
        f"承运工单 · 来自 {buyer_agent_id}（供方 {supplier_agent_id}）· "
        f"{freight.get('origin_city') or '?'}→{freight.get('dest_city') or freight.get('note') or '?'}"
    )

    shared_state = {
        "phase": "await_logistics_ack",
        "logistics_status": "pending_ack",
        "buyer_logistics_ack": False,
        "supplier_logistics_ack": False,  # 兼容旧字段；新链路不再由供应确认
        "logistics_agent_ack": False,
        "order_ticket_id": order_tid,
        "case_id": case_id,
        "buyer_agent_id": buyer_agent_id,
        "supplier_agent_id": supplier_agent_id,
        "initiator_agent_id": buyer_agent_id,
        "quote": {
            "shipping_cost": quoted.get("shipping_cost") or freight.get("amount"),
            "freight_amount": quoted.get("freight_amount") or freight.get("amount"),
            "eta_days": freight.get("eta_days"),
            "distance_km": freight.get("distance_km") or quoted.get("distance_km"),
            "origin_city": freight.get("origin_city"),
            "dest_city": freight.get("dest_city"),
            "currency": freight.get("currency") or "CNY",
            "note": freight.get("note"),
            "shipping_quote_id": freight.get("shipping_quote_id"),
            "capacity_ok": freight.get("amount") is not None
            and float(freight.get("amount") or 0) >= 0
            and not str(quoted.get("freight_note") or "").startswith("未发现")
            and "失败" not in str(quoted.get("freight_note") or ""),
        },
        "logistics_meta": meta,
        "view": "buyer",
    }
    detail = {
        "spawned_at": _now(),
        "from_order_ticket": order_tid,
        "spawned_by": buyer_agent_id,
    }

    _upsert(
        buyer_agent_id,
        ticket_id=tid,
        title=title_buyer,
        peer_agent_id=logistics_id,
        case_id=case_id or None,
        state={**shared_state, "view": "buyer"},
        detail=detail,
    )
    notify.push(
        buyer_agent_id,
        title="物流订单待确认",
        body=f"已由采购询得物流报价，请在「工单待办」与物流双方确认（工单 {tid}）。",
        level="info",
        payload={"ticket_id": tid, "case_id": case_id, "kind": "logistics_spawned"},
    )

    mirror_state = {**shared_state, "view": "logistics"}
    remote = _http_post(
        logistics_id,
        "/api/erp/tickets/mirror-logistics",
        {
            "id": tid,
            "title": title_log,
            "kind": "logistics_order",
            "peer_agent_id": buyer_agent_id,
            "case_id": case_id,
            "state": mirror_state,
            "detail": {**detail, "mirrored_from": buyer_agent_id},
        },
    )
    if not remote.get("ok"):
        _upsert(
            logistics_id,
            ticket_id=tid,
            title=title_log,
            peer_agent_id=buyer_agent_id,
            case_id=case_id or None,
            state=mirror_state,
            detail={**detail, "local_fallback": True},
        )
        notify.push(
            logistics_id,
            title="新承运工单",
            body=f"来自采购 {buyer_agent_id} 的物流订单待确认（{tid}）。",
            level="info",
            payload={"ticket_id": tid, "kind": "logistics_spawned"},
        )
        remote = {"ok": True, "local_fallback": True}

    # 回写采购订单工单
    if order_tid:
        ot = tk.get_ticket(buyer_agent_id, order_tid)
        if ot:
            ost = dict(ot.get("state") or {})
            ost["logistics_ticket_id"] = tid
            ost["logistics_phase"] = "await_logistics_ack"
            ost["shipping_quote_draft"] = shared_state["quote"]
            tk.save_state(buyer_agent_id, order_tid, ost, actor=buyer_agent_id)

    return {
        "ok": True,
        "ticket_id": tid,
        "quote": shared_state["quote"],
        "mirror": remote,
        "freight_note": quoted.get("freight_note"),
        "initiator": buyer_agent_id,
        "supplier_agent_id": supplier_agent_id,
    }


def accept_mirrored_logistics(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    tid = str(payload.get("id") or "")
    if not tid:
        raise ValueError("missing ticket id")
    t = _upsert(
        agent_id,
        ticket_id=tid,
        title=str(payload.get("title") or "物流工单"),
        peer_agent_id=str(payload.get("peer_agent_id") or ""),
        case_id=str(payload.get("case_id") or "") or None,
        state=dict(payload.get("state") or {}),
        detail=dict(payload.get("detail") or {}),
    )
    notify.push(
        agent_id,
        title="新承运工单待确认",
        body=f"物流工单 {tid} 已同步，请确认或取消。",
        level="info",
        payload={"ticket_id": tid, "kind": "logistics_spawned"},
    )
    return t


def ack_logistics(agent_id: str, ticket_id: str, *, sync_peer: bool = True) -> dict[str, Any]:
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    if t.get("status") == tk.STATUS_CLOSED:
        return t
    if t.get("kind") != "logistics_order":
        raise ValueError("非物流工单")
    state = dict(t.get("state") or {})
    if state.get("cancelled"):
        raise ValueError("工单已取消")
    role = _role(agent_id)
    if role == "buyer":
        state["buyer_logistics_ack"] = True
    elif role == "supplier":
        # 旧工单兼容：供应仍可点确认；新链路工单对端是采购，供应不应再收到
        state["supplier_logistics_ack"] = True
    elif role == "logistics":
        state["logistics_agent_ack"] = True
    else:
        raise ValueError("当前角色无法确认物流订单")

    both = bool(_shipper_acked(state) and state.get("logistics_agent_ack"))
    state["logistics_status"] = "both_acked" if both else (
        "shipper_acked" if _shipper_acked(state) else "logistics_acked"
    )
    state["phase"] = "effective" if both else "await_logistics_ack"
    if both:
        state["effective"] = True
        state["effective_at"] = _now()
    t = tk.save_state(agent_id, ticket_id, state, actor=agent_id)

    peer = str(t.get("peer_agent_id") or "")
    if sync_peer and peer:
        _http_post(
            peer,
            f"/api/erp/tickets/{ticket_id}/ack-logistics-peer",
            {"from_agent": agent_id, "role": role, "state": state},
        )

    if both:
        return _on_logistics_effective(agent_id, ticket_id)
    return tk.get_ticket(agent_id, ticket_id) or t


def apply_peer_logistics_ack(agent_id: str, ticket_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    incoming = dict(payload.get("state") or {})
    state = dict(t.get("state") or {})
    state["buyer_logistics_ack"] = bool(
        incoming.get("buyer_logistics_ack") or state.get("buyer_logistics_ack")
    )
    state["supplier_logistics_ack"] = bool(
        incoming.get("supplier_logistics_ack") or state.get("supplier_logistics_ack")
    )
    state["logistics_agent_ack"] = bool(
        incoming.get("logistics_agent_ack") or state.get("logistics_agent_ack")
    )
    both = bool(_shipper_acked(state) and state.get("logistics_agent_ack"))
    state["logistics_status"] = "both_acked" if both else state.get("logistics_status") or "pending_ack"
    state["phase"] = "effective" if both else "await_logistics_ack"
    if both:
        state["effective"] = True
        state["effective_at"] = _now()
    tk.save_state(agent_id, ticket_id, state, actor=payload.get("from_agent"))
    if both:
        return _on_logistics_effective(agent_id, ticket_id)
    return tk.get_ticket(agent_id, ticket_id)  # type: ignore[return-value]


def cancel_logistics(agent_id: str, ticket_id: str, reason: str, *, sync_peer: bool = True) -> dict[str, Any]:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("取消须填写理由")
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    if t.get("kind") != "logistics_order":
        raise ValueError("非物流工单")
    state = dict(t.get("state") or {})
    state["cancelled"] = True
    state["cancel_reason"] = reason
    state["cancelled_by"] = agent_id
    state["cancelled_at"] = _now()
    state["phase"] = "cancelled"
    state["logistics_status"] = "cancelled"
    tk.save_state(agent_id, ticket_id, state, actor=agent_id)
    tk.force_close(agent_id, ticket_id, reason=f"cancel: {reason}")
    peer = str(t.get("peer_agent_id") or "")
    if sync_peer and peer:
        _http_post(
            peer,
            f"/api/erp/tickets/{ticket_id}/cancel-logistics-peer",
            {"from_agent": agent_id, "reason": reason, "state": state},
        )
    notify.push(
        agent_id,
        title="物流订单已取消",
        body=f"工单 {ticket_id} 已取消：{reason}",
        level="warning",
        payload={"ticket_id": ticket_id, "kind": "logistics_cancelled"},
    )
    return tk.get_ticket(agent_id, ticket_id) or t


def apply_peer_logistics_cancel(agent_id: str, ticket_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    state = dict(payload.get("state") or t.get("state") or {})
    state["cancelled"] = True
    state["cancel_reason"] = payload.get("reason") or state.get("cancel_reason")
    state["phase"] = "cancelled"
    tk.save_state(agent_id, ticket_id, state, actor=payload.get("from_agent"))
    if t.get("status") != tk.STATUS_CLOSED:
        tk.force_close(agent_id, ticket_id, reason=f"peer_cancel: {payload.get('reason')}")
    notify.push(
        agent_id,
        title="对端取消了物流订单",
        body=f"{payload.get('from_agent')}：{payload.get('reason')}",
        level="warning",
        payload={"ticket_id": ticket_id, "kind": "logistics_cancelled"},
    )
    return tk.get_ticket(agent_id, ticket_id) or t


def _on_logistics_effective(agent_id: str, ticket_id: str) -> dict[str, Any]:
    t = tk.get_ticket(agent_id, ticket_id)
    if not t:
        raise ValueError("工单不存在")
    state = dict(t.get("state") or {})
    if state.get("buyer_notified"):
        return t
    quote = dict(state.get("quote") or {})
    case_id = t.get("case_id") or state.get("case_id")
    order_tid = state.get("order_ticket_id")
    buyer = str(state.get("buyer_agent_id") or "buyer-a")
    if not buyer.startswith("buyer"):
        buyer = "buyer-a"

    payload = {
        "case_id": case_id,
        "logistics_ticket_id": ticket_id,
        "order_ticket_id": order_tid,
        "shipping_quote": quote,
        "from_agent": agent_id,
        "supplier_agent_id": state.get("supplier_agent_id"),
        "effective": True,
    }
    _http_post(buyer, "/api/erp/shipping-quote/accept", payload)
    # 本地通知
    notify.push(
        agent_id,
        title="物流订单已生效",
        body=f"双方已确认物流；运费 {quote.get('shipping_cost')} 已回传采购方。",
        level="info",
        payload={"ticket_id": ticket_id, "kind": "logistics_effective"},
    )
    state["buyer_notified"] = True
    state["buyer_notified_at"] = _now()
    tk.save_state(agent_id, ticket_id, state, actor=agent_id)
    # 物流单据交换后可回档（简化：直接完结）
    try:
        tk.force_close(agent_id, ticket_id, reason="logistics_effective")
    except Exception:
        pass
    return tk.get_ticket(agent_id, ticket_id) or t
