# -*- coding: utf-8 -*-
"""物流对话 Wit — 目标驱动 + AskUser 时机（与供应侧同构，能力换成承运域）。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from wit import OpenAIChatProvider, WitAgent, WitRuntime, capability

from commerce import chat_sessions as cs
from commerce import notify
from commerce import tickets as tk
from commerce.env_loader import llm_settings
from commerce.goal_runtime import blocker, with_runtime_meta

_AGENT_ID = "logistics"
_DISPLAY = "物流"
_ACTIVE_THREAD_ID: str | None = None
_WORKSPACE = Path(__file__).resolve().parents[1] / "workspaces" / "logistics-wit"

_INSTRUCTIONS = """你是「采联·物流」智能体（承运方）。高度能干：在人类授权内推进承运确认，缺规格就结构化 blockers，禁止编造吨位。

# 目标
报价可读、承运工单由人确认/取消；体积重量必须来自工具/工单，禁止瞎填。

# 原则（Claude Code）
1. 失败先诊断：inspect_goal → 看 blockers。
2. 缺体积/重量：返回 blockers（holder=buyer/supplier），提示对方 flow.backfill_specs；不要问司机「你猜个体积」。
3. 多笔待确认：ui.offer_choices 点选（AskUser 时机）；单笔可直接 ack。
4. 单步查询不弹按钮；禁止「要不要继续」式假选择题。
5. HITL：确认/取消必须经工具。

# 能力
erp.query_tickets · ticket.ack_logistics · ticket.cancel_logistics · partner.inspect_goal · ui.offer_choices · erp.query_notifications

# 表达
结论短；工单用表。有 system_reminder 优先按缺口行动。
"""


def configure(*, agent_id: str = "logistics") -> None:
    global _AGENT_ID, _DISPLAY, _WORKSPACE
    _AGENT_ID = (agent_id or "logistics").strip() or "logistics"
    _DISPLAY = "物流"
    _WORKSPACE = Path(__file__).resolve().parents[1] / "workspaces" / f"{_AGENT_ID}-wit"
    _WORKSPACE.mkdir(parents=True, exist_ok=True)


def _set_active_thread(tid: str | None) -> None:
    global _ACTIVE_THREAD_ID
    _ACTIVE_THREAD_ID = tid


def _open_logistics_tickets() -> list[dict[str, Any]]:
    items = []
    for t in tk.list_tickets(_AGENT_ID, limit=40) or []:
        if t.get("kind") != "logistics_order":
            continue
        st = t.get("state") or {}
        if st.get("cancelled") or st.get("logistics_effective"):
            continue
        items.append(t)
    return items


def _amp_hooks() -> list[Any]:
    return []


def _build_capabilities() -> list[Any]:
    @capability(id="erp.query_notifications", description="通知中心")
    def query_notifications(unread_only: bool = False, limit: int = 20) -> dict[str, Any]:
        items = notify.list_notifications(
            _AGENT_ID, unread_only=bool(unread_only), limit=max(1, min(int(limit or 20), 50))
        )
        return {"ok": True, "items": items, "count": len(items)}

    @capability(id="erp.query_tickets", description="承运工单待办")
    def query_tickets(limit: int = 30) -> dict[str, Any]:
        items = _open_logistics_tickets()[: max(1, min(int(limit or 30), 50))]
        return {
            "ok": True,
            "items": items,
            "count": len(items),
            "presentation_hint": "表：工单号|对方|货物|运费|状态",
        }

    @capability(id="partner.inspect_goal", description="诊断承运侧缺口")
    def inspect_goal() -> dict[str, Any]:
        from commerce.choice_actions import choice, wrap_choice_widget
        from commerce.hitl_policy import recommend_first

        pending = [
            t
            for t in _open_logistics_tickets()
            if not (t.get("state") or {}).get("logistics_ack")
            and not (t.get("state") or {}).get("carrier_ack")
        ]
        # logistics side ack field names vary — treat unacked open tickets
        pending = [t for t in _open_logistics_tickets() if not (t.get("state") or {}).get("logistics_effective")]
        blockers = []
        if len(pending) > 1:
            blockers.append(
                blocker(
                    code="MULTI_LOG_ACK",
                    message=f"{len(pending)} 笔承运单待处理，须人点选",
                    holder="buyer_human",
                    repair_tool="ui.offer_choices",
                )
            )
        for t in pending[:3]:
            st = t.get("state") or {}
            summary = st.get("summary") if isinstance(st.get("summary"), dict) else {}
            if summary.get("volume_m3") is None and (st.get("quote") or {}).get("volume_m3") is None:
                blockers.append(
                    blocker(
                        code="MISSING_VOLUME",
                        message=f"工单 {t.get('id')} 缺体积",
                        holder="buyer",
                        fields=["volume_m3"],
                        repair_tool="flow.backfill_specs",
                        repair_hint="请采购侧补规格后再确认",
                    )
                )
        out = with_runtime_meta(
            {"pending": [t.get("id") for t in pending[:8]]},
            goal="承运工单双方确认生效",
            blockers=blockers,
            next_actions=["ticket.ack_logistics"] if len(pending) == 1 else ["ui.offer_choices", "erp.query_tickets"],
        )
        if len(pending) > 1:
            ch = recommend_first(
                [
                    choice(
                        id=f"ack_{t.get('id')}",
                        label=f"确认 {(t.get('title') or t.get('id') or '')[:20]}",
                        message=f"请 ticket.ack_logistics ticket_id={t.get('id')}",
                    )
                    for t in pending[:6]
                ]
            )
            out["choice_actions"] = wrap_choice_widget(
                case_id=None, prompt="", choices=ch, gate="multi_ticket_ack"
            )
        return out

    @capability(id="ticket.ack_logistics", description="确认承运工单")
    def ack_logistics(ticket_id: str = "") -> dict[str, Any]:
        from commerce import logistics_tickets as lt

        tid = (ticket_id or "").strip()
        pending = _open_logistics_tickets()
        target = tk.get_ticket(_AGENT_ID, tid) if tid else (pending[0] if len(pending) == 1 else None)
        if not target:
            return with_runtime_meta(
                {"error": {"code": "NEED_TICKET", "pending": [t["id"] for t in pending[:8]]}},
                goal="确认承运单",
                blockers=[
                    blocker(
                        code="NEED_TICKET",
                        message="须指定或点选工单",
                        holder="buyer_human",
                        repair_tool="ui.offer_choices",
                    )
                ],
            )
        try:
            out = lt.ack_logistics(_AGENT_ID, target["id"], sync_peer=True)
            return {"ok": True, "ticket_id": target["id"], "result": out, "blockers": []}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "blockers": []}

    @capability(id="ticket.cancel_logistics", description="取消承运工单，必须 reason")
    def cancel_logistics(ticket_id: str = "", reason: str = "") -> dict[str, Any]:
        from commerce import logistics_tickets as lt

        if not (reason or "").strip():
            return {"ok": False, "error": "取消必须写理由"}
        tid = (ticket_id or "").strip()
        pending = _open_logistics_tickets()
        target = tk.get_ticket(_AGENT_ID, tid) if tid else (pending[0] if len(pending) == 1 else None)
        if not target:
            return {"ok": False, "error": "请指定工单号"}
        out = lt.cancel_logistics(_AGENT_ID, target["id"], reason.strip(), sync_peer=True)
        return {"ok": True, "ticket_id": target["id"], "result": out}

    @capability(id="ui.offer_choices", description="AskUser 时机出按钮；推荐项第一")
    def ui_offer_choices(prompt: str = "", choices_json: str = "[]", allow_note: bool = True) -> dict[str, Any]:
        from commerce.choice_actions import normalize_offered_choices
        from commerce.hitl_policy import recommend_first, should_offer_choices

        widget = normalize_offered_choices(
            case_id=None, prompt=prompt or "", choices_json=choices_json, allow_note=allow_note
        )
        ch = recommend_first(list(widget.get("choices") or []))
        widget["choices"] = ch
        if not should_offer_choices(branch_count=len(ch), ambiguous=len(ch) >= 2):
            return {"ok": False, "skipped": True, "reason": "未达 AskUser 时机"}
        return {"ok": True, "choice_actions": widget, "ui_hint": {"form": "choice_actions", **widget}}

    return [
        query_notifications,
        query_tickets,
        inspect_goal,
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
        instructions=_INSTRUCTIONS,
        model=provider,
        capabilities=_build_capabilities(),
        amp_hooks=_amp_hooks(),
        description="采联物流运营助手",
    )
    return WitRuntime(agent, workspace=ws), provider


async def stream_logistics_chat_wit(text: str, *, thread_id: str | None = None):
    runtime, _ = _build_runtime(thread_id=thread_id)
    tid = cs.ensure_thread(_AGENT_ID, thread_id)
    cs.append_message(_AGENT_ID, "user", text, thread_id=tid)
    reply_parts: list[str] = []
    observations: list[dict[str, Any]] = []
    async for ev in runtime.run_stream(text):
        if not isinstance(ev, dict):
            continue
        typ = ev.get("type")
        if typ == "text_delta":
            reply_parts.append(str(ev.get("text") or ""))
            yield ev
        elif typ in {"observation", "tool_result", "tool"}:
            observations.append(ev)
            yield ev
        elif typ == "error":
            yield ev
        else:
            yield ev
    reply = "".join(reply_parts).strip() or "（无文本）"
    # 挂上 inspect 产生的 choice_actions
    widgets = []
    for obs in observations:
        content = obs.get("content") if isinstance(obs.get("content"), dict) else {}
        if not content and isinstance(obs.get("result"), dict):
            content = obs["result"]
        ca = content.get("choice_actions") if isinstance(content, dict) else None
        if ca:
            widgets.append(ca)
    meta = {"engine": "wit", "agent_id": _AGENT_ID}
    if widgets:
        meta["ui_widgets"] = [{"kind": "choice_actions", **w} for w in widgets]
    cs.append_message(_AGENT_ID, "assistant", reply, thread_id=tid, meta=meta)
    yield {"type": "final", "reply": reply, "meta": meta}


async def handle_logistics_chat_wit(text: str, *, thread_id: str | None = None) -> dict[str, Any]:
    final = None
    async for ev in stream_logistics_chat_wit(text, thread_id=thread_id):
        if isinstance(ev, dict) and ev.get("type") == "final":
            final = ev
    return final or {"reply": "", "meta": {}}
