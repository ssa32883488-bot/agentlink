"""组群竞价适合度判定：只决定「要不要让用户选」，不自动开拍。"""
from __future__ import annotations

from typing import Any


def assess_group_auction_suitability(
    *,
    case: dict[str, Any] | None = None,
    quotes: list[dict[str, Any]] | None = None,
    rfq_batch: list[dict[str, Any]] | None = None,
    exclusive_supplier: str | None = None,
) -> dict[str, Any]:
    """
    返回:
      offer: bool — 是否在 UI 出示「组群竞价」选项
      score: 0..100
      reasons: 适合的理由
      blockers: 不适合的理由
    """
    case = case or {}
    brief = case.get("brief") or {}
    reasons: list[str] = []
    blockers: list[str] = []

    if exclusive_supplier:
        blockers.append(f"用户已指定独家 {exclusive_supplier}")

    shortlist = case.get("shortlist") or []
    short_n = len([p for p in shortlist if p.get("agent_id")])

    ok_rows: list[dict[str, Any]] = []
    # 优先 rfq_batch（V1 并行询价）
    for r in rfq_batch or case.get("rfq_batch") or []:
        if not isinstance(r, dict):
            continue
        if r.get("status") == "ok" and r.get("grand_total") is not None:
            ok_rows.append(r)
    if not ok_rows:
        for q in quotes or case.get("quotes") or []:
            if not isinstance(q, dict):
                continue
            pay = q.get("payload") if isinstance(q.get("payload"), dict) else q
            if pay.get("grand_total") is not None or pay.get("unit_price") is not None:
                ok_rows.append(pay)

    ok_n = len(ok_rows)
    if ok_n < 2:
        blockers.append(f"有效报价不足 2 家（当前 {ok_n}）")
    else:
        reasons.append(f"有效报价 {ok_n} 家，具备多方可比性")

    if short_n >= 3:
        reasons.append(f"短名单 {short_n} 家，适合组群协商")
    elif short_n == 2:
        reasons.append("短名单 2 家，可开组群但竞争性一般")
    elif short_n < 2 and ok_n < 2:
        blockers.append("短名单过窄")

    try:
        qty = int(brief.get("quantity") or 0)
    except (TypeError, ValueError):
        qty = 0
    if qty >= 200:
        reasons.append(f"采购量 {qty} 具备再竞一轮的体量")
    elif qty > 0:
        blockers.append(f"采购量 {qty} 偏小，组群开销可能不划算")

    # 胶着度：最低与次低 grand 差距
    totals: list[float] = []
    freight_ratios: list[float] = []
    for r in ok_rows:
        try:
            g = float(r.get("grand_total"))
        except (TypeError, ValueError):
            continue
        totals.append(g)
        goods = r.get("goods_total")
        fr = r.get("freight")
        if isinstance(fr, dict):
            famt = fr.get("amount")
        else:
            famt = r.get("freight_amount")
        try:
            if goods is not None and float(goods) > 0 and famt is not None:
                freight_ratios.append(float(famt) / float(goods))
        except (TypeError, ValueError):
            pass

    totals.sort()
    if len(totals) >= 2 and totals[0] > 0:
        gap_ratio = (totals[1] - totals[0]) / totals[0]
        if gap_ratio <= 0.08:
            reasons.append(f"到岸价胶着（次低仅高 {gap_ratio*100:.1f}%），适合盲拍再分胜负")
        elif gap_ratio <= 0.15:
            reasons.append(f"到岸价较接近（差距 {gap_ratio*100:.1f}%），组群仍可能优化 TCO")
        else:
            blockers.append(f"最低价已明显领先（差距 {gap_ratio*100:.1f}%），可直接选商或议价")

    if freight_ratios and sum(freight_ratios) / len(freight_ratios) >= 0.08:
        reasons.append("运费占比较高，组群合入物流 TCO 更有价值")

    product = str(brief.get("product_name") or "").strip()
    if not product:
        blockers.append("案主体 product_name 缺失")
    else:
        reasons.append(f"单一主体「{product}」，规格可对齐竞价")

    # 打分
    score = 40
    score += min(30, ok_n * 10)
    if qty >= 500:
        score += 15
    elif qty >= 200:
        score += 8
    if len(totals) >= 2 and totals[0] > 0 and (totals[1] - totals[0]) / totals[0] <= 0.12:
        score += 20
    if freight_ratios and sum(freight_ratios) / len(freight_ratios) >= 0.08:
        score += 10
    if exclusive_supplier:
        score = 0
    if ok_n < 2:
        score = min(score, 25)
    score = max(0, min(100, score))

    # 出示选项：有硬阻断则否；否则 score>=55 或（≥2 家且量≥200）
    hard = any(
        x.startswith("用户已指定") or x.startswith("有效报价不足") or x.startswith("案主体")
        for x in blockers
    )
    offer = (not hard) and (score >= 55 or (ok_n >= 2 and qty >= 200 and not exclusive_supplier))

    return {
        "offer": offer,
        "score": score,
        "reasons": reasons,
        "blockers": blockers,
        "ok_quote_count": ok_n,
        "shortlist_count": short_n,
        "quantity": qty,
        "hint": (
            "需求多方可比且值得再协商时，可发起组群竞价，由供应盲拍、物流旁听合 TCO，再选最经济合适方案。"
            if offer
            else "当前更适合议价或直接选商；组群竞价选项已隐藏。"
        ),
    }
