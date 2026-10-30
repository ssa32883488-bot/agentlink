# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any

from commerce_v2.widgets import attach_pending, choice_widget


def set_ask(case: dict[str, Any], prompt: str, choices: list[dict[str, Any]]) -> dict[str, Any]:
    w = choice_widget(case, prompt=prompt, choices=choices)
    attach_pending(case, w)
    return w


def clear_ask(case: dict[str, Any]) -> None:
    attach_pending(case, None)


def match_choice(text: str, choices: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not choices:
        return None
    t = (text or "").strip()
    for c in choices:
        for key in (c.get("id"), c.get("label"), c.get("message")):
            if key and str(key) in t:
                return c
        msg = str(c.get("message") or "")
        if msg and t == msg:
            return c
    # 短名单消息
    return None


def parse_shortlist_ids(text: str) -> list[str] | None:
    """解析 UI 短名单确认话术中的 candidate_id（含 logistics）。"""
    if "短名单" not in (text or "") and "rfq.send_batch" not in (text or "") and "确认组群" not in (text or ""):
        return None
    # 优先捞全部合法 agent id
    ones = re.findall(r"supplier-[a-c]|logistics", text or "")
    if ones:
        # 保序去重
        out: list[str] = []
        for x in ones:
            if x not in out:
                out.append(x)
        return out
    m = re.search(r"candidate_id[：:]\s*([^\s（(]+)", text or "")
    if not m:
        return None
    raw = m.group(1)
    ids = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
    return ids or None
