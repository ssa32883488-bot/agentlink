"""供应商对话：Wit + DeepSeek（与采购同款 LLM/编排）+ 供应侧 Capability。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from wit import (
    AmpAccessLoggingHooks,
    OpenAIChatProvider,
    WitAgent,
    WitRuntime,
    capability,
)

from commerce import chat_sessions as cs
from commerce import chat_supplier as csup
from commerce import notify
from commerce import order_tickets as ot
from commerce import supplier_service as ss
from commerce import tickets as tk
from commerce.env_loader import llm_settings

_AGENT_ID = "supplier-a"
_DISPLAY = "供应商A"
_WORKSPACE = Path(__file__).resolve().parents[1] / "workspaces" / "supplier-a-wit"
_ACTIVE_THREAD_ID: str | None = None

_INSTRUCTIONS_TMPL = """你是「采联·{display}」智能体（Partner / 供应侧）。高度能干：在人类授权内持续推进本厂目标，直到必须人确认或完成。

# 目标
服务本厂人员：价目/库存/优惠属实可查；询价箱可读；销售订单与物流工单由人确认或取消。你是应答方，不替采购规划跨厂物流。

# 规划原则（套皮 Claude Code：原则驱动，禁止穷举 if）
1. 失败先诊断：工具 error/blockers 先读再换战术；不要空转抱怨。
2. 缺数找持有方：缺工单号且多笔待办 → ui.offer_choices 让人点选；缺取消理由 → 问人；缺规格被采购追问 → 用 catalog/物理规格如实答，禁止编造。
3. 单步直做：查库存/优惠/通知直接调工具，不要为琐事弹按钮。
4. 出按钮时机（AskUserQuestion 同款）：仅当歧义、≥2 路径、或不可逆确认前须择一；禁止用按钮问「要不要继续/计划好不好」。
5. 推荐项放第一个并标「（推荐）」。
6. HITL：确认/取消订单与物流必须经工具；禁止假装已点确认。

# 能力
erp.query_catalog · erp.query_promotions · erp.query_rfq_inbox · erp.query_notifications · erp.query_tickets
ticket.ack_order / cancel_order · ticket.ack_logistics / cancel_logistics · ui.offer_choices · partner.inspect_goal

# 定价
挂牌价不议；优惠只认 promotions（erp.query_promotions）。禁止说「没有优惠字段」或编造折扣。

# 表达
结论一两句；价目/优惠/工单用 Markdown 表。有 system_reminder 优先按缺口行动。
"""

INSTRUCTIONS = _INSTRUCTIONS_TMPL.format(display=_DISPLAY)


def configure(*, agent_id: str = "supplier-a") -> None:
    global _AGENT_ID, _DISPLAY, _WORKSPACE, INSTRUCTIONS
    _AGENT_ID = (agent_id or "supplier-a").strip() or "supplier-a"
    labels = {"supplier-a": "供应商A", "supplier-b": "供应商B", "supplier-c": "供应商C"}
    _DISPLAY = labels.get(_AGENT_ID, _AGENT_ID)
    _WORKSPACE = Path(__file__).resolve().parents[1] / "workspaces" / f"{_AGENT_ID}-wit"
    INSTRUCTIONS = _INSTRUCTIONS_TMPL.format(display=_DISPLAY)
    csup.configure(agent_id=_AGENT_ID)


def _set_active_thread(thread_id: str | None) -> None:
    global _ACTIVE_THREAD_ID
    _ACTIVE_THREAD_ID = thread_id


def _amp_hooks() -> list[Any]:
    return [AmpAccessLoggingHooks()]


def _open_order_tickets() -> list[dict[str, Any]]:
    return [t for t in tk.list_tickets(_AGENT_ID, status="open", limit=30) if t.get("kind") == "order"]


def _open_logistics_tickets() -> list[dict[str, Any]]:
    return [t for t in tk.list_tickets(_AGENT_ID, status="open", limit=30) if t.get("kind") == "logistics_order"]


def _load_policy() -> dict[str, Any]:
    import yaml

    root = Path(__file__).resolve().parents[1]
    folder = _AGENT_ID.replace("-", "_")
    for path in (
        root / "agents" / _AGENT_ID / "policy.yaml",
        root / "agents" / folder / "policy.yaml",
    ):
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
    return {}


def _promotions_payload() -> dict[str, Any]:
    """结构化输出本厂优惠政策 + 可读摘要（来自 policy.yaml，已上线）。"""
    pol = _load_policy()
    promos = pol.get("promotions") if isinstance(pol.get("promotions"), dict) else {}
    merchant = pol.get("merchant") if isinstance(pol.get("merchant"), dict) else {}
    summaries: list[str] = []
    for tier in promos.get("line_qty_discount") or []:
        if not isinstance(tier, dict):
            continue
        skus = ",".join(str(s) for s in (tier.get("skus") or []))
        pct = float(tier.get("discount_pct") or 0) * 100
        summaries.append(
            f"{tier.get('label') or '单品满量折扣'}：SKU[{skus}] 满 {tier.get('threshold_qty')} 件 → 减 {pct:.0f}%"
        )
    for tier in promos.get("full_reduction") or []:
        if not isinstance(tier, dict):
            continue
        bits = [str(tier.get("label") or "满减")]
        if tier.get("threshold_amount") is not None:
            bits.append(f"货价满 {tier['threshold_amount']}")
        if tier.get("threshold_qty") is not None:
            bits.append(f"满 {tier['threshold_qty']} 件")
        if tier.get("reduce_amount") is not None:
            bits.append(f"减 {tier['reduce_amount']}")
        elif tier.get("reduce_pct") is not None:
            bits.append(f"减 {float(tier['reduce_pct'])*100:.0f}%")
        summaries.append(" / ".join(bits))
    sub = promos.get("cross_province_subsidy")
    if isinstance(sub, dict) and sub.get("enabled"):
        summaries.append(
            str(sub.get("label") or "跨省运费补贴")
            + f"：运费补贴 {float(sub.get('subsidy_pct_of_freight') or 0)*100:.0f}%"
            + ("（审核不确定）" if sub.get("uncertain", True) else "")
        )
    return {
        "ok": True,
        "agent_id": _AGENT_ID,
        "trade_name": merchant.get("trade_name") or _DISPLAY,
        "pricing_mode": "list_plus_promo_only",
        "note": "挂牌价不议；优惠只认下列已公示活动（不在价目行字段里，而在 promotions 政策中）",
        "promotions": promos,
        "summaries": summaries,
        "has_promotions": bool(summaries),
    }


def _build_capabilities() -> list[Any]:
    @capability(
        id="erp.query_catalog",
        description="查询本厂库存与挂牌价目（可售、MOQ、交期）；回执含 promotions 摘要，问优惠时也可据此回答。",
    )
    def query_catalog(limit: int = 50) -> dict[str, Any]:
        items = ss.list_catalog(_AGENT_ID)[: max(1, min(int(limit or 50), 100))]
        promo = _promotions_payload()
        return {
            "ok": True,
            "agent_id": _AGENT_ID,
            "pricing_mode": "list_plus_promo_only",
            "count": len(items),
            "items": [
                {
                    "code": i.get("code"),
                    "name": i.get("name"),
                    "unit": i.get("unit"),
                    "list_price": i.get("list_price"),
                    "on_hand": i.get("on_hand"),
                    "moq": i.get("moq"),
                    "lead_time_days": i.get("lead_time_days"),
                    "strategy_tag": i.get("strategy_tag"),
                }
                for i in items
            ],
            "promotions": promo.get("promotions") or {},
            "promotion_summaries": promo.get("summaries") or [],
            "has_promotions": promo.get("has_promotions"),
            "promo_note": promo.get("note"),
            "presentation_hint": "用 Markdown 表格展示价目（SKU|名称|挂牌单价|可用库存|单位|交期|备注）。",
        }

    @capability(
        id="erp.query_promotions",
        description="查询本厂已公示优惠政策（满量折扣/满减/跨省运费补贴）。用户问优惠、活动、折扣时必须调用。",
    )
    def query_promotions() -> dict[str, Any]:
        out = _promotions_payload()
        out["presentation_hint"] = "用 Markdown 表格展示优惠（规则|适用SKU|门槛|优惠|说明）。"
        return out

    @capability(id="erp.query_rfq_inbox", description="查询采购方发来的询价箱记录。")
    def query_rfq_inbox(limit: int = 20) -> dict[str, Any]:
        items = ss.list_rfq_inbox(_AGENT_ID, limit=max(1, min(int(limit or 20), 50)))
        return {
            "ok": True,
            "count": len(items),
            "items": items,
            "presentation_hint": "用 Markdown 表格展示询价箱（询价ID|对方|物料|数量|时间|状态）。",
        }

    @capability(id="erp.query_notifications", description="查询通知中心；unread_only=true 仅未读。")
    def query_notifications(unread_only: bool = False, limit: int = 20) -> dict[str, Any]:
        items = notify.list_notifications(
            _AGENT_ID, unread_only=bool(unread_only), limit=max(1, min(int(limit or 20), 50))
        )
        return {
            "ok": True,
            "count": len(items),
            "unread": len([n for n in items if not n.get("read")]),
            "items": items,
            "presentation_hint": "用 Markdown 表格展示通知（时间|标题|已读|摘要）。",
        }

    @capability(id="erp.query_tickets", description="查询销售订单/物流工单待办。kind=order|logistics|all")
    def query_tickets(kind: str = "all", limit: int = 30) -> dict[str, Any]:
        k = (kind or "all").strip().lower()
        orders = _open_order_tickets()
        logs = _open_logistics_tickets()
        hint = "用 Markdown 表格展示工单（工单号|类型|对方|物料|数量|状态）。"
        if k in {"order", "orders", "sales"}:
            return {"ok": True, "kind": "order", "items": orders[:limit], "presentation_hint": hint}
        if k in {"logistics", "log", "shipping"}:
            return {"ok": True, "kind": "logistics", "items": logs[:limit], "presentation_hint": hint}
        return {
            "ok": True,
            "kind": "all",
            "orders": orders[:limit],
            "logistics": logs[:limit],
            "order_count": len(orders),
            "logistics_count": len(logs),
            "presentation_hint": hint,
        }

    @capability(
        id="partner.inspect_goal",
        description="诊断本厂侧缺口（多笔待确认工单等）。不知下一步时先调。",
    )
    def partner_inspect_goal() -> dict[str, Any]:
        from commerce import goal_runtime as gr

        orders = [t for t in _open_order_tickets() if not (t.get("state") or {}).get("supplier_order_ack")]
        logs = [t for t in _open_logistics_tickets() if not (t.get("state") or {}).get("supplier_logistics_ack")]
        blockers: list[dict[str, Any]] = []
        if len(orders) > 1:
            blockers.append(
                gr.blocker(
                    code="MULTI_ORDER_ACK",
                    message=f"有 {len(orders)} 笔销售单待确认，须人点选工单号",
                    holder="buyer_human",
                    repair_tool="ui.offer_choices",
                )
            )
        if len(logs) > 1:
            blockers.append(
                gr.blocker(
                    code="MULTI_LOG_ACK",
                    message=f"有 {len(logs)} 笔物流单待确认，须人点选",
                    holder="buyer_human",
                    repair_tool="ui.offer_choices",
                )
            )
        next_actions: list[str] = []
        if len(orders) == 1:
            next_actions.append("ticket.ack_order")
        if len(logs) == 1:
            next_actions.append("ticket.ack_logistics")
        if blockers:
            next_actions = ["ui.offer_choices"]
        out = gr.with_runtime_meta(
            {
                "agent_id": _AGENT_ID,
                "pending_orders": [t.get("id") for t in orders[:8]],
                "pending_logistics": [t.get("id") for t in logs[:8]],
            },
            goal="本厂待办清零（人确认后）",
            blockers=blockers,
            next_actions=next_actions or ["erp.query_tickets"],
        )
        if blockers:
            from commerce.choice_actions import choice, wrap_choice_widget
            from commerce.hitl_policy import recommend_first

            ch = []
            for t in orders[:5]:
                ch.append(
                    choice(
                        id=f"ack_{t.get('id')}",
                        label=f"确认订单 {(t.get('title') or t.get('id') or '')[:18]}",
                        message=f"请 ticket.ack_order ticket_id={t.get('id')}",
                    )
                )
            for t in logs[:5]:
                ch.append(
                    choice(
                        id=f"acklog_{t.get('id')}",
                        label=f"确认物流 {(t.get('title') or t.get('id') or '')[:18]}",
                        message=f"请 ticket.ack_logistics ticket_id={t.get('id')}",
                    )
                )
            if ch:
                out["choice_actions"] = wrap_choice_widget(
                    case_id=None, prompt="", choices=recommend_first(ch), gate="multi_ticket_ack"
                )
        return out

    @capability(id="ticket.ack_order", description="确认销售订单已生成。ticket_id 可空：仅当待确认恰好一笔时自动取。")
    def ack_order(ticket_id: str = "") -> dict[str, Any]:
        from commerce import goal_runtime as gr
        from commerce.hitl_policy import recommend_first
        from commerce.choice_actions import choice, wrap_choice_widget

        tid = (ticket_id or "").strip()
        pending = [t for t in _open_order_tickets() if not (t.get("state") or {}).get("supplier_order_ack")]
        target = tk.get_ticket(_AGENT_ID, tid) if tid else (pending[0] if len(pending) == 1 else None)
        if not target:
            ch = recommend_first(
                [
                    choice(
                        id=f"ack_{t.get('id')}",
                        label=f"确认 {(t.get('title') or t.get('id') or '')[:20]}",
                        message=f"请 ticket.ack_order ticket_id={t.get('id')}",
                    )
                    for t in pending[:6]
                ]
            ) if pending else []
            return gr.with_runtime_meta(
                {
                    "error": {"code": "NEED_TICKET", "message": "请指定工单号", "pending": [t["id"] for t in pending[:8]]},
                    "choice_actions": wrap_choice_widget(case_id=None, prompt="", choices=ch, gate="multi_ticket_ack")
                    if ch
                    else None,
                },
                goal="确认正确的销售订单",
                blockers=[
                    gr.blocker(
                        code="NEED_TICKET",
                        message="多笔或不明确，须人点选工单",
                        holder="buyer_human",
                        repair_tool="ui.offer_choices",
                    )
                ]
                if len(pending) != 1
                else [],
            )
        try:
            out = ot.ack_order_generated(_AGENT_ID, target["id"], sync_peer=True)
            return {"ok": True, "ticket_id": target["id"], "result": out}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": {"code": "ACK_FAIL", "message": str(exc)}}

    @capability(id="ticket.cancel_order", description="取消销售订单；必须提供 reason。")
    def cancel_order(ticket_id: str = "", reason: str = "") -> dict[str, Any]:
        tid = (ticket_id or "").strip()
        reason = (reason or "").strip()
        pending = _open_order_tickets()
        target = tk.get_ticket(_AGENT_ID, tid) if tid else (pending[0] if len(pending) == 1 else None)
        if not reason:
            return {"ok": False, "error": {"code": "NEED_REASON", "message": "取消订单必须写明理由"}}
        if not target:
            return {
                "ok": False,
                "error": {"code": "NEED_TICKET", "message": "请指定工单号", "pending": [t["id"] for t in pending[:8]]},
            }
        try:
            out = ot.cancel_order(_AGENT_ID, target["id"], reason, sync_peer=True)
            return {"ok": True, "ticket_id": target["id"], "result": out}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": {"code": "CANCEL_FAIL", "message": str(exc)}}

    @capability(id="ticket.ack_logistics", description="确认物流工单。ticket_id 可空：仅当待确认恰好一笔时自动取。")
    def ack_logistics(ticket_id: str = "") -> dict[str, Any]:
        from commerce import logistics_tickets as lt

        tid = (ticket_id or "").strip()
        pending = [t for t in _open_logistics_tickets() if not (t.get("state") or {}).get("supplier_logistics_ack")]
        target = tk.get_ticket(_AGENT_ID, tid) if tid else (pending[0] if len(pending) == 1 else None)
        if not target:
            return {
                "ok": False,
                "error": {
                    "code": "NEED_TICKET",
                    "message": "没有可确认的物流工单或请指定编号",
                    "pending": [t["id"] for t in pending[:8]],
                },
            }
        try:
            out = lt.ack_logistics(_AGENT_ID, target["id"], sync_peer=True)
            return {"ok": True, "ticket_id": target["id"], "result": out}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": {"code": "ACK_FAIL", "message": str(exc)}}

    @capability(id="ticket.cancel_logistics", description="取消物流工单；必须提供 reason。")
    def cancel_logistics(ticket_id: str = "", reason: str = "") -> dict[str, Any]:
        from commerce import logistics_tickets as lt

        tid = (ticket_id or "").strip()
        reason = (reason or "").strip()
        pending = _open_logistics_tickets()
        target = tk.get_ticket(_AGENT_ID, tid) if tid else (pending[0] if len(pending) == 1 else None)
        if not reason:
            return {"ok": False, "error": {"code": "NEED_REASON", "message": "取消物流必须写明理由"}}
        if not target:
            return {
                "ok": False,
                "error": {"code": "NEED_TICKET", "message": "请指定物流工单号", "pending": [t["id"] for t in pending[:8]]},
            }
        try:
            out = lt.cancel_logistics(_AGENT_ID, target["id"], reason, sync_peer=True)
            return {"ok": True, "ticket_id": target["id"], "result": out}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": {"code": "CANCEL_FAIL", "message": str(exc)}}

    @capability(
        id="ui.offer_choices",
        description=(
            "AskUserQuestion 同款：歧义/多路径/不可逆前择一时出按钮。"
            "choices_json=[{id,label,message,primary?,hint?}]；推荐项放第一并标（推荐）。"
            "禁止用于「要不要继续」；禁止琐碎单步查询时弹窗。"
        ),
    )
    def ui_offer_choices(
        prompt: str = "",
        choices_json: str = "[]",
        allow_note: bool = True,
    ) -> dict[str, Any]:
        from commerce.choice_actions import normalize_offered_choices
        from commerce.hitl_policy import recommend_first, should_offer_choices

        widget = normalize_offered_choices(
            case_id=None,
            prompt=prompt or "",
            choices_json=choices_json,
            allow_note=allow_note,
        )
        ch = recommend_first(list(widget.get("choices") or []))
        widget["choices"] = ch
        widget["prompt"] = prompt or ""
        if not should_offer_choices(branch_count=len(ch), ambiguous=len(ch) >= 2):
            return {
                "ok": False,
                "skipped": True,
                "reason": "未达 AskUser 时机（无歧义/单路径）；请直接调业务工具",
                "choice_actions": None,
            }
        return {
            "ok": True,
            "choice_actions": widget,
            "ui_hint": {"form": "choice_actions", **(widget or {})},
            "hitl": {"prompt": prompt or "", "gate": "user_choice"},
        }

    return [
        query_catalog,
        query_promotions,
        query_rfq_inbox,
        query_notifications,
        query_tickets,
        partner_inspect_goal,
        ack_order,
        cancel_order,
        ack_logistics,
        cancel_logistics,
        ui_offer_choices,
    ]


def _build_runtime(*, thread_id: str | None = None) -> tuple[Any, OpenAIChatProvider]:
    settings = llm_settings()
    provider = OpenAIChatProvider(
        model=settings["model"],
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        temperature=0.2,
    )
    tid = cs.ensure_thread(_AGENT_ID, thread_id)
    _set_active_thread(tid)
    cs.set_active_thread(_AGENT_ID, tid)
    ws = _WORKSPACE / "threads" / tid
    ws.mkdir(parents=True, exist_ok=True)
    agent = WitAgent(
        id=f"{_AGENT_ID}:{tid}",
        display_name=_DISPLAY,
        instructions=INSTRUCTIONS,
        model=provider,
        capabilities=_build_capabilities(),
        amp_hooks=_amp_hooks(),
        description=f"采联{_DISPLAY}运营助手（Wit + DeepSeek）·窗 {tid}",
    )
    return WitRuntime(agent, workspace=ws), provider


def _as_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _extract_ui_widgets(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    widgets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obs in observations or []:
        if not isinstance(obs, dict):
            continue
        content = (
            _as_dict(obs.get("result"))
            or _as_dict(obs.get("content"))
            or _as_dict(obs.get("observation"))
            or _as_dict(obs.get("output"))
        )
        if not content:
            continue
        hint = content.get("ui_hint") if isinstance(content.get("ui_hint"), dict) else {}
        ca = content.get("choice_actions")
        choices = None
        prompt = None
        allow_note = True
        if isinstance(ca, dict) and ca.get("choices"):
            choices = ca.get("choices")
            prompt = ca.get("prompt")
            allow_note = bool(ca.get("allow_note", True))
        elif hint.get("form") == "choice_actions" and hint.get("choices"):
            choices = hint.get("choices")
            prompt = hint.get("title") or hint.get("prompt")
            allow_note = bool(hint.get("allow_note", True))
        if choices:
            key = f"choices:{len(choices)}:{prompt}"
            if key in seen:
                continue
            seen.add(key)
            widgets.append(
                {
                    "kind": "choice_actions",
                    "prompt": prompt or "请点选下一步（可填补充说明）",
                    "allow_note": allow_note,
                    "choices": choices,
                    "ui_hint": hint or {"form": "choice_actions"},
                    "hitl": content.get("hitl") or (ca or {}).get("hitl"),
                }
            )
    return widgets


def _finalize_from_run(
    *,
    reply: str,
    observations: list[dict[str, Any]],
    status: str | None = None,
    iterations: int | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    reply = (reply or "").strip() or "（模型未返回文本）"
    widgets = _extract_ui_widgets(observations)
    meta: dict[str, Any] = {"intent": "wit_chat", "engine": "wit"}
    if status is not None:
        meta["status"] = status
    if iterations is not None:
        meta["iterations"] = iterations
    if widgets:
        meta["ui_widgets"] = widgets
        meta["intent"] = "choice_hitl"
    tid = thread_id or cs.active_thread_id(_AGENT_ID)
    meta["thread_id"] = tid
    csup._add_conv(_AGENT_ID, "assistant", reply, thread_id=tid, meta=meta)  # noqa: SLF001
    out: dict[str, Any] = {
        "reply": reply,
        "intent": meta["intent"],
        "engine": "wit",
        "thread_id": tid,
    }
    if widgets:
        out["ui_widgets"] = widgets
    return out


def _tool_status_label(name: str, *, done: bool = False) -> str:
    raw = (name or "").strip()
    labels = {
        "erp.query_catalog": ("正在查询库存与价目…", "库存价目查询完成"),
        "erp.query_promotions": ("正在读取本厂优惠政策…", "优惠政策已就绪"),
        "erp.query_rfq_inbox": ("正在查询询价箱…", "询价箱查询完成"),
        "erp.query_notifications": ("正在查询通知…", "通知查询完成"),
        "erp.query_tickets": ("正在查询工单待办…", "工单查询完成"),
        "ticket.ack_order": ("正在确认销售订单…", "销售订单已确认"),
        "ticket.cancel_order": ("正在取消销售订单…", "销售订单已取消"),
        "ticket.ack_logistics": ("正在确认物流工单…", "物流工单已确认"),
        "ticket.cancel_logistics": ("正在取消物流工单…", "物流工单已取消"),
        "ui.offer_choices": ("正在生成可点选按钮…", "请点选下一步"),
    }
    if raw in labels:
        return labels[raw][1 if done else 0]
    return (f"工具已完成：{raw}" if done else f"正在调用工具 {raw or '…'}…")


def _tool_name_from_event(data: dict[str, Any], ev: Any) -> str:
    tool = data.get("tool_call") or data.get("tool") or {}
    if isinstance(tool, dict):
        return str(tool.get("name") or tool.get("id") or "")
    return str(data.get("tool_name") or getattr(ev, "name", "") or "")


async def stream_supplier_chat_wit(text: str, *, thread_id: str | None = None):
    from commerce.progress import drain_status_queue, make_queue_reporter, reset_progress, set_progress

    text = (text or "").strip()
    tid = cs.ensure_thread(_AGENT_ID, thread_id)
    cs.set_active_thread(_AGENT_ID, tid)
    csup._add_conv(_AGENT_ID, "user", text, thread_id=tid)  # noqa: SLF001

    settings = llm_settings()
    if not settings["api_key"]:
        reply = "未配置 LLM_API_KEY，无法使用 Wit 对话。"
        csup._add_conv(_AGENT_ID, "assistant", reply, thread_id=tid, meta={"intent": "llm_config_error"})  # noqa: SLF001
        yield {"type": "error", "message": reply, "intent": "llm_config_error", "engine": "wit", "thread_id": tid}
        return

    runtime, provider = _build_runtime(thread_id=tid)
    tokens: list[str] = []
    observations: list[dict[str, Any]] = []
    final_reply = ""
    status = "ok"
    iterations = 0
    status_q: asyncio.Queue = asyncio.Queue(maxsize=200)
    progress_token = set_progress(make_queue_reporter(status_q))
    active_tool = ""

    async def _flush_progress():
        for item in await drain_status_queue(status_q):
            yield item

    try:
        yield {"type": "status", "text": "正在理解你的意图…", "phase": "think", "engine": "wit"}
        stream = runtime.astream_events(text).__aiter__()
        next_ev = asyncio.create_task(stream.__anext__())
        while True:
            async for item in _flush_progress():
                yield item
            done, _ = await asyncio.wait({next_ev}, timeout=0.12)
            if not done:
                continue
            try:
                ev = next_ev.result()
            except StopAsyncIteration:
                break
            next_ev = asyncio.create_task(stream.__anext__())

            name = getattr(ev, "event", "") or ""
            data = dict(getattr(ev, "data", None) or {})
            if name in ("model.start", "llm.start", "step.start") and not tokens:
                yield {"type": "status", "text": "模型思考中…", "phase": "think"}
            elif name == "model.delta" and data.get("type") == "text":
                piece = str(data.get("text") or "")
                if piece:
                    if not tokens:
                        yield {"type": "status", "text": "正在组织回复…", "phase": "reply"}
                    tokens.append(piece)
                    yield {"type": "token", "text": piece}
            elif name == "tool.start":
                active_tool = _tool_name_from_event(data, ev)
                yield {
                    "type": "status",
                    "text": _tool_status_label(active_tool, done=False),
                    "phase": "tool",
                    "tool": active_tool,
                }
            elif name in ("tool.end", "tool.result"):
                tool_name = _tool_name_from_event(data, ev) or active_tool
                yield {
                    "type": "status",
                    "text": _tool_status_label(tool_name, done=True),
                    "phase": "tool_done",
                    "tool": tool_name,
                }
                active_tool = ""
            elif name == "step.end":
                for obs in data.get("observations") or []:
                    if isinstance(obs, dict):
                        observations.append(obs)
            elif name == "run.end":
                result = data.get("result") or {}
                if isinstance(result, dict):
                    parts = result.get("output_parts") or []
                    texts = []
                    for part in parts:
                        if isinstance(part, dict) and part.get("type") == "text":
                            texts.append(str(part.get("text") or ""))
                    final_reply = "".join(texts).strip()
                    for obs in result.get("observations") or []:
                        if isinstance(obs, dict):
                            observations.append(obs)
                    status = str(result.get("status") or status)
                    try:
                        iterations = int(result.get("iterations") or 0)
                    except (TypeError, ValueError):
                        iterations = 0

        if not next_ev.done():
            next_ev.cancel()
        async for item in _flush_progress():
            yield item
        reply = final_reply or "".join(tokens)
        out = _finalize_from_run(
            reply=reply,
            observations=observations,
            status=status,
            iterations=iterations,
            thread_id=tid,
        )
        yield {"type": "status", "text": "回复就绪", "phase": "done"}
        yield {"type": "done", **out}
    except Exception as exc:  # noqa: BLE001
        reply = f"Wit/LLM 调用失败：{exc}"
        csup._add_conv(_AGENT_ID, "assistant", reply, thread_id=tid, meta={"intent": "wit_error", "error": str(exc)})  # noqa: SLF001
        yield {"type": "error", "message": reply, "intent": "wit_error", "engine": "wit", "thread_id": tid}
    finally:
        reset_progress(progress_token)
        await provider.aclose()


async def handle_supplier_chat_wit(text: str, *, thread_id: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"reply": "", "intent": "wit_chat", "engine": "wit"}
    async for ev in stream_supplier_chat_wit(text, thread_id=thread_id):
        if ev.get("type") == "done":
            out = {k: v for k, v in ev.items() if k != "type"}
        elif ev.get("type") == "error":
            out = {
                "reply": ev.get("message") or "调用失败",
                "intent": ev.get("intent") or "wit_error",
                "engine": "wit",
                "thread_id": ev.get("thread_id"),
            }
    return out
