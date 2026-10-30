"""订单成立全链路回溯：采购案审计 + 工单事件 + 代码层路径 + 梧桐 AMP/AIP 交互。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from commerce import mailbox as mb
from commerce import tickets as tk

_ROOT = Path(__file__).resolve().parents[1]
_ACCESS_LOG = _ROOT / "logs" / "amp_access.jsonl"
_MESSAGE_LOG = _ROOT / "logs" / "amp_message.jsonl"
_INTERACTIONS = _ROOT / "logs" / "interactions.jsonl"

# 订单成立的代码层路径（按业务阶段标注模块/入口，供审计「代码级」回溯）
CODE_CHAIN: list[dict[str, Any]] = [
    {
        "id": "case_create",
        "title": "创建采购案",
        "events": ("created",),
        "modules": [
            "commerce.procurement_case.create_case",
            "commerce.flow_service / chat_buyer_wit",
        ],
    },
    {
        "id": "discover",
        "title": "梧桐 ADP 发现供应商",
        "events": ("discover_done", "discover"),
        "modules": [
            "commerce.flow_service.step_discover",
            "commerce.discovery.discover_suppliers",
            "梧桐 ACPs ADP → /acps-adp-v2/discover",
        ],
        "platform": "adp",
    },
    {
        "id": "shortlist",
        "title": "短名单 HITL 确认",
        "events": ("hitl_approve", "hitl_edit", "confirm_shortlist", "shortlist"),
        "modules": [
            "commerce.flow_service.step_hitl / step_confirm_shortlist",
            "ui shortlistDock → flow.confirm_shortlist",
        ],
    },
    {
        "id": "rfq",
        "title": "AIP 询价 / 报价",
        "events": ("rfq_done", "sourcing", "quote"),
        "modules": [
            "commerce.flow_service.step_rfq_and_compare",
            "agentlink_runtime.aip_client_util.call_partner",
            "commerce.amp_log.record_access（Access+Message → Kafka amp.*）",
        ],
        "platform": "aip+amp",
    },
    {
        "id": "compare",
        "title": "比价与决策",
        "events": ("compare_done", "decide_order", "decide_negotiate", "decide_auction"),
        "modules": [
            "agents.buyer_a.graph.compare_quotes",
            "commerce.flow_service.step_decide",
        ],
    },
    {
        "id": "order_draft",
        "title": "订单草案 + 双边工单",
        "events": ("decide_order", "order_ticket_created"),
        "modules": [
            "agents.buyer_a.graph.build_order_draft",
            "commerce.order_tickets.spawn_order_ticket_from_case",
            "POST /api/erp/tickets/mirror-order",
        ],
    },
    {
        "id": "order_ack",
        "title": "双方确认订单已生成",
        "events": ("state_saved", "order_ack", "ack"),
        "modules": [
            "commerce.order_tickets.ack_order_generated",
            "POST /api/erp/tickets/{id}/ack-order",
        ],
    },
    {
        "id": "docs",
        "title": "电子订单 / 发票互发",
        "events": ("e_order_sent", "e_invoice_sent", "e_order_received", "e_invoice_received", "final_mails_bound", "docs_sent"),
        "modules": [
            "commerce.order_tickets._dispatch_final_docs",
            "commerce.mailbox.compose_order_and_invoice / send_mail",
        ],
    },
    {
        "id": "archive",
        "title": "工单完结回档",
        "events": ("archived", "force_closed"),
        "modules": ["commerce.tickets._maybe_archive"],
    },
]


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    s = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _read_jsonl_tail(path: Path, *, max_lines: int = 8000) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def query_amp(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    aics: set[str] | None = None,
    task_ids: set[str] | None = None,
    limit: int = 120,
) -> dict[str, list[dict[str, Any]]]:
    """从本地 AMP Access/Message 日志筛出与订单相关的梧桐交互。"""
    access_all = _read_jsonl_tail(_ACCESS_LOG)
    message_all = _read_jsonl_tail(_MESSAGE_LOG)
    aics = {a for a in (aics or set()) if a}
    task_ids = {t for t in (task_ids or set()) if t}

    def _match(row: dict[str, Any]) -> bool:
        ts = _parse_ts(row.get("timestamp") or row.get("ts"))
        if since and ts and ts < since:
            return False
        if until and ts and ts > until:
            return False
        tid = str(row.get("correlationId") or row.get("correlation_id") or "")
        if task_ids and tid and tid in task_ids:
            return True
        if not aics and not task_ids:
            return True
        local = str(row.get("aic") or "")
        body = row.get("body") or {}
        peer = ""
        if isinstance(body, dict):
            peer = str(
                ((body.get("callee") or {}).get("aic"))
                or ((body.get("caller") or {}).get("aic"))
                or ((body.get("attributes") or {}).get("peerAic") or "")
            )
        attrs = (body.get("attributes") or {}) if isinstance(body, dict) else {}
        if aics and (local in aics or peer in aics or str(attrs.get("peerAic") or "") in aics):
            return True
        if task_ids and tid in task_ids:
            return True
        # 时间窗内无 AIC 过滤时：若仅有时间条件也保留（由调用方收窄）
        if since and not aics and not task_ids:
            return True
        return False

    access = [r for r in access_all if _match(r)][-limit:]
    messages = [r for r in message_all if _match(r)][-limit:]
    return {"access": list(reversed(access[-limit:])), "messages": list(reversed(messages[-limit:]))}


def query_aip_interactions(
    *,
    agent_id: str | None = None,
    business_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    peer_aics: set[str] | None = None,
    task_ids: set[str] | None = None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    rows = _read_jsonl_tail(_INTERACTIONS, max_lines=6000)
    peer_aics = peer_aics or set()
    task_ids = task_ids or set()
    out: list[dict[str, Any]] = []
    for row in reversed(rows):
        if agent_id and row.get("local_agent_id") not in (agent_id, None) and row.get("local_agent_id") != agent_id:
            # 允许同案跨角色：不过度过滤 local
            pass
        if business_id and row.get("business_id") and row.get("business_id") != business_id:
            continue
        ts = _parse_ts(row.get("ts"))
        if since and ts and ts < since:
            continue
        if until and ts and ts > until:
            continue
        tid = str(row.get("task_id") or "")
        to_aic = str(row.get("to_aic") or "")
        from_aic = str(row.get("from_aic") or "")
        if task_ids and tid and tid not in task_ids:
            if peer_aics and to_aic not in peer_aics and from_aic not in peer_aics:
                continue
            if not peer_aics:
                continue
        elif peer_aics and to_aic and from_aic:
            if to_aic not in peer_aics and from_aic not in peer_aics and tid not in task_ids:
                # 仍允许 business_id / 时间窗命中
                if not business_id:
                    if since is None:
                        continue
        out.append(
            {
                "ts": row.get("ts"),
                "direction": row.get("direction"),
                "local_agent_id": row.get("local_agent_id"),
                "from_aic": from_aic,
                "to_aic": to_aic,
                "to_url": row.get("to_url"),
                "task_id": tid,
                "session_id": row.get("session_id"),
                "state": row.get("state"),
                "business_id": row.get("business_id"),
                "req_schema": row.get("req_schema"),
                "res_schema": row.get("res_schema"),
                "message": row.get("message"),
                "request": row.get("request"),
                "response": row.get("response"),
            }
        )
        if len(out) >= limit:
            break
    return out


def _collect_task_ids(case: dict[str, Any] | None) -> set[str]:
    ids: set[str] = set()
    if not case:
        return ids
    for q in case.get("quotes") or []:
        for key in ("task_id", "aip_task_id"):
            if q.get(key):
                ids.add(str(q[key]))
        pay = q.get("payload") if isinstance(q.get("payload"), dict) else {}
        if pay.get("task_id"):
            ids.add(str(pay["task_id"]))
        meta = q.get("meta") if isinstance(q.get("meta"), dict) else {}
        if meta.get("task_id"):
            ids.add(str(meta["task_id"]))
    for round_ in case.get("negotiate_rounds") or []:
        if isinstance(round_, dict) and round_.get("task_id"):
            ids.add(str(round_["task_id"]))
    return ids


def _collect_aics(case: dict[str, Any] | None, ticket: dict[str, Any] | None) -> set[str]:
    aics: set[str] = set()
    if case:
        for c in case.get("candidates") or []:
            if c.get("aic"):
                aics.add(str(c["aic"]))
        for c in case.get("shortlist") or []:
            if isinstance(c, dict) and c.get("aic"):
                aics.add(str(c["aic"]))
            elif isinstance(c, str):
                pass
        for q in case.get("quotes") or []:
            pay = q.get("payload") if isinstance(q.get("payload"), dict) else {}
            for key in ("supplier_aic", "aic", "partner_aic"):
                if pay.get(key):
                    aics.add(str(pay[key]))
                if q.get(key):
                    aics.add(str(q[key]))
    return aics


def _annotate_code_chain(case_audit: list[dict[str, Any]], ticket_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把实际事件挂到代码层路径节点上。"""
    event_blob = []
    for a in case_audit:
        event_blob.append({"at": a.get("at"), "event": a.get("event"), "state": a.get("state"), "source": "case"})
    for e in ticket_events:
        event_blob.append(
            {
                "at": e.get("created_at"),
                "event": e.get("event"),
                "actor": e.get("actor"),
                "detail": e.get("detail"),
                "source": "ticket",
            }
        )

    out: list[dict[str, Any]] = []
    for node in CODE_CHAIN:
        keys = tuple(k.lower() for k in node["events"])
        hits = []
        for ev in event_blob:
            name = str(ev.get("event") or "").lower()
            if any(k in name for k in keys):
                hits.append(ev)
        out.append(
            {
                "id": node["id"],
                "title": node["title"],
                "modules": node["modules"],
                "platform": node.get("platform"),
                "hit": bool(hits),
                "events": hits[-8:],
            }
        )
    return out


def build_provenance(
    agent_id: str,
    *,
    case_id: str | None = None,
    ticket_id: str | None = None,
) -> dict[str, Any]:
    ticket = tk.get_ticket(agent_id, ticket_id) if ticket_id else None
    if not case_id and ticket:
        case_id = ticket.get("case_id") or ((ticket.get("state") or {}).get("summary") or {}).get("case_id")

    case: dict[str, Any] | None = None
    if case_id:
        try:
            from commerce import procurement_case as pc

            case = pc.get_case(case_id)
        except Exception:
            case = None

    if not ticket and case_id:
        # 按 case 找本侧订单工单
        for t in tk.list_tickets(agent_id, limit=80):
            if t.get("case_id") == case_id or (t.get("kind") == "order" and case_id in str(t.get("id") or "")):
                ticket = t
                ticket_id = t.get("id")
                break

    ticket_events = tk.list_events(agent_id, ticket_id, limit=200) if ticket_id else []
    mails = mb.list_mail(agent_id, ticket_id=ticket_id, limit=40) if ticket_id else []
    # 也按 case 主题松散匹配订单/发票
    if case_id and not mails:
        all_m = mb.list_mail(agent_id, limit=80)
        mails = [m for m in all_m if case_id in str(m.get("body") or "") or case_id in str(m.get("subject") or "")]

    case_audit = list((case or {}).get("audit") or [])
    code_chain = _annotate_code_chain(case_audit, ticket_events)

    created = _parse_ts((case or {}).get("created_at") or (ticket or {}).get("created_at"))
    updated = _parse_ts((case or {}).get("updated_at") or (ticket or {}).get("updated_at")) or datetime.now(timezone.utc)
    since = (created - timedelta(minutes=5)) if created else (updated - timedelta(hours=6))
    until = updated + timedelta(minutes=30)

    task_ids = _collect_task_ids(case)
    for e in ticket_events:
        d = e.get("detail") or {}
        if isinstance(d, dict) and d.get("task_id"):
            task_ids.add(str(d["task_id"]))
    aics = _collect_aics(case, ticket)

    amp = query_amp(since=since, until=until, aics=aics or None, task_ids=task_ids or None, limit=100)
    # 若 AIC/task 过滤过严导致空，退回时间窗
    if not amp["access"] and not amp["messages"] and created:
        amp = query_amp(since=since, until=until, limit=60)

    aip = query_aip_interactions(
        agent_id=agent_id,
        business_id=case_id,
        since=since,
        until=until,
        peer_aics=aics or None,
        task_ids=task_ids or None,
        limit=60,
    )
    if not aip and case_id:
        aip = query_aip_interactions(business_id=case_id, limit=40)

    discovery_meta = (case or {}).get("discovery_meta") or {}
    platform_summary = {
        "adp": {
            "source": discovery_meta.get("source"),
            "discovery_url": discovery_meta.get("discovery_url"),
            "query": discovery_meta.get("query"),
            "elapsed_ms": discovery_meta.get("elapsed_ms"),
            "cache_hit": discovery_meta.get("cache_hit"),
            "platform_error": discovery_meta.get("platform_error"),
            "candidates": [
                {
                    "agent_id": c.get("agent_id"),
                    "name": c.get("name"),
                    "aic": c.get("aic"),
                    "source": c.get("source") or c.get("source_label"),
                    "endpoint": c.get("endpoint"),
                    "skills": (c.get("skills") or [])[:6],
                }
                for c in ((case or {}).get("candidates") or [])
            ],
        },
        "amp": {
            "access_count": len(amp["access"]),
            "message_count": len(amp["messages"]),
            "task_ids": sorted(task_ids)[:40],
            "access": amp["access"],
            "messages": amp["messages"],
        },
        "aip_interactions": aip,
    }

    docs = []
    for m in mails:
        if m.get("mail_kind") in ("e_order", "e_invoice"):
            docs.append(
                {
                    "id": m.get("id"),
                    "mail_kind": m.get("mail_kind"),
                    "subject": m.get("subject"),
                    "folder": m.get("folder"),
                    "created_at": m.get("created_at"),
                    "from_agent": m.get("from_agent"),
                    "to_agent": m.get("to_agent"),
                    "attachment": m.get("attachment"),
                    "body": m.get("body"),
                    "meta": m.get("meta"),
                }
            )

    return {
        "agent_id": agent_id,
        "case_id": case_id,
        "ticket_id": ticket_id or (ticket or {}).get("id"),
        "case": {
            "state": (case or {}).get("state"),
            "brief": (case or {}).get("brief"),
            "selected_supplier": (case or {}).get("selected_supplier"),
            "order_draft": (case or {}).get("order_draft"),
            "comparison": (case or {}).get("comparison"),
            "audit": case_audit,
            "created_at": (case or {}).get("created_at"),
            "updated_at": (case or {}).get("updated_at"),
        }
        if case
        else None,
        "ticket": ticket,
        "ticket_events": ticket_events,
        "code_chain": code_chain,
        "documents": docs,
        "platform": platform_summary,
        "completion": tk.completion_flags(ticket) if ticket else None,
    }
