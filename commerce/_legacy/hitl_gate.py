"""HITL 门禁：四态决策 + 可选上下文（编排层，不改协议报文）。

注意：gate 只表示「当前需要人确认的高风险点」，不是强制 10 步脚本。
Agent 应按用户意图规划；hitl 仅在副作用前拦截。
"""
from __future__ import annotations

from typing import Any

# 门禁上下文：供 UI/工具返回；对话层不应强制「步骤 x/10」套话
GATE_META: dict[str, dict[str, Any]] = {
    "confirm_shortlist": {
        "role": "Leader·采购商A",
        "phase": "shortlist",
        "hint": "可确认询价对象、改选，或拒绝本次短名单",
    },
    "compare_decide": {
        "role": "Leader·采购商A",
        "phase": "compare",
        "hint": "可下单草案、议价、竞价，或拒绝本轮报价",
    },
    "negotiate_review": {
        "role": "Leader·采购商A",
        "phase": "negotiate",
        "hint": "可再议价、改竞价、选商下单，或拒绝",
    },
    "bid_review": {
        "role": "Leader·采购商A",
        "phase": "auction",
        "hint": "可按竞价结果选商下单，或拒绝",
    },
    "request_shipping": {
        "role": "Leader·采购商A",
        "phase": "shipping",
        "hint": "可自己联系物流、请对方联系物流，或暂缓/拒绝草案——不要只逼供应侧出运价",
    },
    "bilateral_confirm": {
        "role": "Leader·采购商A",
        "phase": "contract",
        "hint": "可采购方确认合同，或拒绝",
    },
    "supplier_confirm": {
        "role": "Leader·采购商A",
        "phase": "contract",
        "hint": "可请求供应商确认，或作废",
    },
    "activate": {
        "role": "Leader·采购商A",
        "phase": "activate",
        "hint": "可激活订单，或拒绝激活",
    },
}
# 兼容旧引用
STEP_META = GATE_META

DECISIONS = ("approve", "edit", "reject", "respond")


def make_hitl(
    gate: str,
    prompt: str,
    *,
    options: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = GATE_META.get(gate) or {"role": "Leader·采购商A", "phase": gate, "hint": prompt}
    body: dict[str, Any] = {
        "gate": gate,
        "prompt": prompt,
        "role": meta.get("role") or "Leader·采购商A",
        "phase": meta.get("phase") or gate,
        "hint": meta.get("hint") or prompt,
        # 兼容旧前端字段；不再表示强制进度条
        "next_hint": meta.get("hint") or prompt,
        "decisions": list(DECISIONS),
        "options": options or [],
        "status": "awaiting",
    }
    if extra:
        body.update(extra)
    return body


def narrative_line(hitl: dict[str, Any] | None) -> str:
    """状态播报用短句，不作固定步骤套话。"""
    if not hitl:
        return ""
    role = hitl.get("role") or "Leader"
    prompt = hitl.get("prompt") or ""
    phase = hitl.get("phase") or hitl.get("gate") or ""
    return f"{role} 待确认（{phase}）：{prompt}"
