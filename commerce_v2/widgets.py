# -*- coding: utf-8 -*-
"""UI widget 形状：兼容 ui/static/app.js shortlistDock / choiceDock。"""
from __future__ import annotations

from typing import Any


def shortlist_widget(case: dict[str, Any]) -> dict[str, Any]:
    cands = []
    for c in case.get("candidates") or []:
        cands.append(
            {
                "candidate_id": c.get("agent_id") or c.get("candidate_id"),
                "agent_id": c.get("agent_id"),
                "trade_name": c.get("title") or c.get("trade_name") or c.get("agent_id"),
                "city": c.get("city") or "",
                "address": c.get("blurb") or c.get("address") or "",
                "biz": c.get("blurb") or "供应智能体",
                "checked": True,
            }
        )
    return {
        "kind": "shortlist_confirm",
        "case_id": case.get("case_id"),
        "title": "请选择要交互的供应智能体（断点①）",
        "min_select": 1,
        "max_select": max(1, len(cands)),
        "candidates": cands,
    }


def choice_widget(
    case: dict[str, Any],
    *,
    prompt: str,
    choices: list[dict[str, Any]],
    allow_note: bool = True,
) -> dict[str, Any]:
    return {
        "kind": "choice_actions",
        "case_id": case.get("case_id"),
        "prompt": prompt,
        "allow_note": allow_note,
        "choices": choices,
    }


def attach_pending(case: dict[str, Any], widget: dict[str, Any] | None) -> None:
    if widget and widget.get("kind") == "choice_actions":
        case["pending_choices"] = widget
        case["hitl_pending"] = {"gate": "ask_user", "phase": "ask_user"}
    elif widget and widget.get("kind") == "shortlist_confirm":
        case["pending_choices"] = None
        case["hitl_pending"] = {"gate": "confirm_shortlist", "phase": "confirm_shortlist"}
    else:
        case["pending_choices"] = None
        case["hitl_pending"] = None
