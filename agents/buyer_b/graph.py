from __future__ import annotations

from typing import Any

from agents.buyer_a.graph import build_order_draft, build_quote_request, compare_quotes, run_buyer_plan

__all__ = [
    "build_order_draft",
    "build_quote_request",
    "compare_quotes",
    "run_buyer_plan",
    "check_quick_reorder_policy",
]


def check_quick_reorder_policy(policy: dict[str, Any], pr: dict[str, Any], supplier_aic: str) -> str | None:
    """返回拒绝原因；None 表示通过。"""
    whitelist = set(policy.get("whitelist_suppliers") or [])
    if whitelist and supplier_aic not in whitelist:
        return f"supplier not in whitelist: {supplier_aic}"
    qty = int(pr.get("quantity") or 0)
    max_total = float(policy.get("max_total_cost") or 0)
    # 快速路径用预算字段做限额闸（不出站）
    budget = (pr.get("budget") or {}).get("max_total_cost")
    if budget is not None and float(budget) > max_total:
        return f"over quick-reorder limit: budget {budget} > {max_total}"
    if qty <= 0:
        return "invalid quantity"
    return None
