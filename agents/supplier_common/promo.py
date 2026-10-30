"""供应商促销：单品满量折扣 + 满减 + 跨省运费补贴。议价用门槛换条件。"""
from __future__ import annotations

from typing import Any


def _merchant_province(policy: dict[str, Any]) -> str:
    m = policy.get("merchant") if isinstance(policy.get("merchant"), dict) else {}
    return str(m.get("province") or policy.get("province") or "").strip()


def _dest_province(rfq_payload: dict[str, Any] | None) -> str:
    rfq = rfq_payload or {}
    dest = rfq.get("destination") if isinstance(rfq.get("destination"), dict) else {}
    delivery = rfq.get("delivery") if isinstance(rfq.get("delivery"), dict) else {}
    return str(
        rfq.get("dest_province")
        or dest.get("province")
        or delivery.get("province")
        or "河北"
    ).strip()


def list_line_qty_discounts(policy: dict[str, Any]) -> list[dict[str, Any]]:
    promos = policy.get("promotions") if isinstance(policy.get("promotions"), dict) else {}
    rows = promos.get("line_qty_discount") or policy.get("line_qty_discount") or []
    out: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        skus = [str(s).upper() for s in (row.get("skus") or [])]
        thr = row.get("threshold_qty")
        pct = row.get("discount_pct")
        if not skus or thr is None or pct is None:
            continue
        out.append(
            {
                "label": str(row.get("label") or "单品满量折扣"),
                "skus": skus,
                "threshold_qty": int(thr),
                "discount_pct": float(pct),
            }
        )
    return out


def apply_line_qty_unit_price(
    policy: dict[str, Any],
    *,
    sku: str,
    qty: int,
    unit_price: float,
) -> tuple[float, dict[str, Any] | None]:
    """命中单品满量折扣时返回折后单价。"""
    code = (sku or "").upper().strip()
    best: dict[str, Any] | None = None
    best_unit = float(unit_price)
    for tier in list_line_qty_discounts(policy):
        if code not in tier["skus"]:
            continue
        if qty < int(tier["threshold_qty"]):
            continue
        cand = round(float(unit_price) * (1.0 - float(tier["discount_pct"])), 2)
        if cand < best_unit:
            best_unit = cand
            best = {
                **tier,
                "applied": True,
                "list_unit": float(unit_price),
                "unit_after": cand,
                "save_per_unit": round(float(unit_price) - cand, 2),
            }
    return best_unit, best


def next_line_qty_gap(
    policy: dict[str, Any],
    *,
    sku: str,
    qty: int,
    unit_price: float,
) -> dict[str, Any] | None:
    code = (sku or "").upper().strip()
    candidates: list[dict[str, Any]] = []
    for tier in list_line_qty_discounts(policy):
        if code and code not in tier["skus"]:
            continue
        need = int(tier["threshold_qty"])
        if qty >= need:
            continue
        list_u = float(unit_price)
        disc_u = round(list_u * (1.0 - float(tier["discount_pct"])), 2)
        goods_now = round(list_u * qty, 2)
        goods_at = round(disc_u * need, 2)
        extra = round(list_u * (need - qty), 2)
        save_vs_list = round(list_u * need - goods_at, 2)
        net = round(goods_at - goods_now, 2)
        candidates.append(
            {
                "tier": {**tier, "kind": "line_qty_discount"},
                "target_qty": need,
                "qty_gap": need - qty,
                "extra_goods_spend": extra,
                "promo_save": save_vs_list,
                "net_extra_spend": net,
                "worth_it": net <= list_u * (need - qty) * 0.5,
                "hint": (
                    f"加购 {need - qty} 件可达「{tier['label']}」，"
                    f"折后单价约 {disc_u:.2f}（目录价 {list_u:.2f}）"
                ),
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c["qty_gap"], c["net_extra_spend"]))
    return candidates[0]


def list_full_reductions(policy: dict[str, Any]) -> list[dict[str, Any]]:
    promos = policy.get("promotions") if isinstance(policy.get("promotions"), dict) else {}
    rows = promos.get("full_reduction") or policy.get("full_reduction") or []
    out: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        thr_amt = row.get("threshold_amount")
        thr_qty = row.get("threshold_qty")
        reduce_amt = row.get("reduce_amount")
        reduce_pct = row.get("reduce_pct")
        if thr_amt is None and thr_qty is None:
            continue
        out.append(
            {
                "label": str(row.get("label") or "满减"),
                "threshold_amount": float(thr_amt) if thr_amt is not None else None,
                "threshold_qty": int(thr_qty) if thr_qty is not None else None,
                "reduce_amount": float(reduce_amt) if reduce_amt is not None else None,
                "reduce_pct": float(reduce_pct) if reduce_pct is not None else None,
            }
        )
    return out


def cross_province_subsidy_cfg(policy: dict[str, Any]) -> dict[str, Any] | None:
    promos = policy.get("promotions") if isinstance(policy.get("promotions"), dict) else {}
    cfg = promos.get("cross_province_subsidy") or policy.get("cross_province_subsidy")
    if not isinstance(cfg, dict) or not cfg.get("enabled"):
        return None
    return cfg


def _reduction_value(tier: dict[str, Any], goods: float) -> float:
    if tier.get("reduce_amount") is not None:
        return float(tier["reduce_amount"])
    if tier.get("reduce_pct") is not None:
        return round(goods * float(tier["reduce_pct"]), 2)
    return 0.0


def _tier_met(tier: dict[str, Any], *, qty: int, goods: float) -> bool:
    ok = True
    if tier.get("threshold_amount") is not None:
        ok = ok and goods >= float(tier["threshold_amount"])
    if tier.get("threshold_qty") is not None:
        ok = ok and qty >= int(tier["threshold_qty"])
    return ok


def best_applicable_full_reduction(
    policy: dict[str, Any], *, qty: int, unit_price: float
) -> tuple[dict[str, Any] | None, float]:
    goods = round(float(unit_price) * int(qty), 2)
    applicable = [
        t for t in list_full_reductions(policy) if _tier_met(t, qty=qty, goods=goods)
    ]
    if not applicable:
        return None, 0.0
    best = max(applicable, key=lambda t: _reduction_value(t, goods))
    return best, _reduction_value(best, goods)


def next_full_reduction_gap(
    policy: dict[str, Any], *, qty: int, unit_price: float
) -> dict[str, Any] | None:
    """距离下一档满减还差多少（件数或货价）。"""
    goods = round(float(unit_price) * int(qty), 2)
    candidates: list[dict[str, Any]] = []
    for tier in list_full_reductions(policy):
        if _tier_met(tier, qty=qty, goods=goods):
            continue
        need_qty = qty
        if tier.get("threshold_qty") is not None:
            need_qty = max(need_qty, int(tier["threshold_qty"]))
        if tier.get("threshold_amount") is not None and unit_price > 0:
            need_by_amt = int((float(tier["threshold_amount"]) + unit_price - 1e-9) // unit_price)
            if float(unit_price) * need_by_amt < float(tier["threshold_amount"]):
                need_by_amt += 1
            need_qty = max(need_qty, need_by_amt)
        if need_qty <= qty:
            continue
        goods_at = round(float(unit_price) * need_qty, 2)
        save = _reduction_value(tier, goods_at)
        extra_spend = round(float(unit_price) * (need_qty - qty), 2)
        net = round(extra_spend - save, 2)
        candidates.append(
            {
                "tier": {**tier, "kind": "full_reduction"},
                "target_qty": need_qty,
                "qty_gap": need_qty - qty,
                "extra_goods_spend": extra_spend,
                "promo_save": save,
                "net_extra_spend": net,
                "worth_it": net <= 0,
                "hint": (
                    f"加购 {need_qty - qty} 件可达「{tier['label']}」，"
                    f"多花货价 {extra_spend:.0f}、减免 {save:.0f}，净增支出约 {net:.0f}"
                ),
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c["net_extra_spend"], c["qty_gap"]))
    return candidates[0]


def apply_cross_province_subsidy(
    policy: dict[str, Any],
    *,
    qty: int,
    freight: float | None,
    dest_province: str,
) -> dict[str, Any]:
    cfg = cross_province_subsidy_cfg(policy)
    base = {
        "eligible": False,
        "applied": False,
        "uncertain": False,
        "subsidy_amount": 0.0,
        "freight_after": freight,
        "note": None,
    }
    if not cfg or freight is None:
        return base
    origin = str(cfg.get("origin_province") or _merchant_province(policy) or "")
    dest = (dest_province or "").strip()
    min_qty = int(cfg.get("min_qty") or 0)
    if not origin or not dest or origin == dest:
        base["note"] = "收货省与发货省相同，不适用跨省补贴"
        return base
    if qty < min_qty:
        base["eligible"] = True
        base["uncertain"] = bool(cfg.get("uncertain", True))
        base["note"] = (
            f"跨省补贴需满 {min_qty} 件（当前 {qty}）；"
            f"{cfg.get('note') or '以当地审核为准'}"
        )
        return base
    pct = float(cfg.get("subsidy_pct_of_freight") or 0)
    flat = float(cfg.get("subsidy_per_unit") or 0) * qty
    subsidy = round(max(float(freight) * pct, 0) + flat, 2)
    subsidy = min(subsidy, float(freight))
    base.update(
        {
            "eligible": True,
            "applied": subsidy > 0,
            "uncertain": bool(cfg.get("uncertain", True)),
            "subsidy_amount": subsidy,
            "freight_after": round(float(freight) - subsidy, 2),
            "note": cfg.get("note")
            or f"{origin}→{dest} 跨省出省运费补贴（演示政策，审核存在不确定性）",
            "origin_province": origin,
            "dest_province": dest,
        }
    )
    return base


def settle_quote_economics(
    policy: dict[str, Any],
    *,
    qty: int,
    unit_price: float,
    freight: float | None = None,
    rfq_payload: dict[str, Any] | None = None,
    sku: str | None = None,
) -> dict[str, Any]:
    """按当前量结算：单品折扣、货价、满减、补贴后运费、TCO。"""
    qty = int(qty)
    rfq = rfq_payload or {}
    specs = rfq.get("specifications") if isinstance(rfq.get("specifications"), dict) else {}
    sku_code = (
        (sku or "").upper()
        or str(specs.get("sku") or specs.get("material_code") or "").upper()
        or str(rfq.get("product_name") or policy.get("default_sku") or "").upper()
    )
    # 从目录还原 list 价，避免对已折后单价再打折
    list_unit = float(unit_price)
    for row in policy.get("catalog") or []:
        if isinstance(row, dict) and str(row.get("sku") or "").upper() == sku_code:
            if row.get("unit_price") is not None:
                list_unit = float(row["unit_price"])
            break
    unit, line_meta = apply_line_qty_unit_price(
        policy, sku=sku_code, qty=qty, unit_price=list_unit
    )
    if line_meta is None:
        # 无单品折扣：沿用调用方单价（可能含议价善意让价）
        unit = float(unit_price)
    goods = round(unit * qty, 2)
    line_save = round(max(0.0, list_unit * qty - goods), 2) if line_meta else 0.0
    tier, save = best_applicable_full_reduction(policy, qty=qty, unit_price=unit)
    goods_after = round(max(0.0, goods - save), 2)
    dest_p = _dest_province(rfq_payload)
    sub = apply_cross_province_subsidy(
        policy, qty=qty, freight=freight, dest_province=dest_p
    )
    freight_after = sub.get("freight_after")
    tco = goods_after + (float(freight_after) if freight_after is not None else 0.0)

    gap_full = next_full_reduction_gap(policy, qty=qty, unit_price=unit)
    gap_line = next_line_qty_gap(policy, sku=sku_code, qty=qty, unit_price=list_unit)
    # 下一档：优先净增支出更小 / 加量更少
    gaps = [g for g in (gap_full, gap_line) if g]
    gaps.sort(key=lambda c: (c["net_extra_spend"], c["qty_gap"]))
    gap = gaps[0] if gaps else None

    hints: list[str] = []
    for t in list_line_qty_discounts(policy):
        hints.append(
            f"{t['label']} / 满{t['threshold_qty']}件 / 减{float(t['discount_pct'])*100:.0f}%"
        )
    for t in list_full_reductions(policy):
        bits = [t["label"]]
        if t.get("threshold_qty") is not None:
            bits.append(f"满{t['threshold_qty']}件")
        if t.get("threshold_amount") is not None:
            bits.append(f"满货价{t['threshold_amount']:.0f}")
        if t.get("reduce_amount") is not None:
            bits.append(f"减{t['reduce_amount']:.0f}")
        elif t.get("reduce_pct") is not None:
            bits.append(f"减{float(t['reduce_pct'])*100:.0f}%")
        hints.append(" / ".join(bits))
    cfg = cross_province_subsidy_cfg(policy)
    if cfg:
        hints.append(
            str(cfg.get("label") or "跨省运费补贴")
            + ("（审核不确定）" if cfg.get("uncertain", True) else "")
        )
    return {
        "quantity": qty,
        "sku": sku_code or None,
        "unit_price": unit,
        "list_unit_price": list_unit,
        "goods_total": goods,
        "line_qty_discount": line_meta,
        "line_qty_save": line_save,
        "full_reduction": tier,
        "full_reduction_save": save,
        "goods_after_promo": goods_after,
        "freight": freight,
        "cross_province_subsidy": sub,
        "freight_after_subsidy": freight_after,
        "tco": round(tco, 2) if freight_after is not None or freight is not None else round(goods_after, 2),
        "next_tier": gap,
        "policy_hints": hints,
        "dest_province": dest_p,
        "origin_province": _merchant_province(policy),
    }


def goodwill_unit_price(
    policy: dict[str, Any], *, previous_unit: float, quantity: int
) -> float:
    """已取消私下底价/让价：单价不因议价轮次下调；优惠只走 promotions。

    保留函数签名供议价管线调用；quantity / policy 仅占位兼容。
    """
    _ = (policy, quantity)
    return round(float(previous_unit), 2)


def promo_leverage_amount(economics: dict[str, Any]) -> float:
    """采购议价可挖空间：已触发优惠 + 下一档可达节省 + 跨省补贴（若有）。"""
    room = float(economics.get("line_qty_save") or 0) + float(
        economics.get("full_reduction_save") or 0
    )
    gap = economics.get("next_tier")
    if isinstance(gap, dict):
        room += float(gap.get("promo_save") or 0)
    sub = economics.get("cross_province_subsidy")
    if isinstance(sub, dict):
        room += float(sub.get("subsidy_amount") or 0)
    return round(max(0.0, room), 2)


def build_bargain_narrative(
    policy: dict[str, Any],
    *,
    economics: dict[str, Any],
    goal_text: str | None,
) -> dict[str, Any]:
    """生成谈判话术与可选项：不是单刀压价。"""
    merchant = policy.get("merchant") if isinstance(policy.get("merchant"), dict) else {}
    name = str(merchant.get("trade_name") or "本厂")
    hints = list(economics.get("policy_hints") or [])
    gap = economics.get("next_tier")
    sub = economics.get("cross_province_subsidy") or {}
    options: list[dict[str, Any]] = [
        {
            "option_id": "keep_qty",
            "title": "维持现量",
            "quantity": economics["quantity"],
            "summary": "挂牌价不变；吃已触发的满减/单品折扣/补贴（若有）",
        }
    ]
    if gap:
        options.append(
            {
                "option_id": "reach_full_reduction",
                "title": "凑活动门槛",
                "quantity": gap["target_qty"],
                "summary": gap["hint"],
                "net_extra_spend": gap["net_extra_spend"],
            }
        )
    if sub.get("eligible") and not sub.get("applied"):
        cfg = cross_province_subsidy_cfg(policy) or {}
        options.append(
            {
                "option_id": "reach_cross_province",
                "title": "冲跨省补贴门槛",
                "quantity": max(int(economics["quantity"]), int(cfg.get("min_qty") or economics["quantity"])),
                "summary": sub.get("note") or "加量后可申请跨省运费补贴（审核不确定）",
                "uncertain": True,
            }
        )
    elif sub.get("applied"):
        options.append(
            {
                "option_id": "take_subsidy",
                "title": "走跨省补贴路径",
                "quantity": economics["quantity"],
                "summary": sub.get("note"),
                "uncertain": bool(sub.get("uncertain")),
                "subsidy_amount": sub.get("subsidy_amount"),
            }
        )

    talk = (
        f"{name}：理解贵方「{goal_text or '优化综合成本'}」。"
        "本厂不设私下底价，挂牌价不议；优惠只认已公示的活动门槛"
        "（满量折扣/满减/跨省补贴）。更划算的路径通常是凑门槛或拆单。"
    )
    if economics.get("line_qty_save"):
        talk += f" 当前量已享受单品折扣约 {economics['line_qty_save']:.0f} 元。"
    if economics.get("full_reduction_save"):
        talk += f" 当前量已享受满减约 {economics['full_reduction_save']:.0f} 元。"
    elif gap:
        talk += f" {gap['hint']}。"
    if sub.get("eligible"):
        talk += (
            " 另外山西出省还有运费补贴政策，但要过审核、结果有不确定性，"
            "适合预算相对宽裕、能接受沟通等待的路径。"
        )
    return {
        "talk_track": talk,
        "counter_options": options,
        "policy_hints": hints,
        "negotiation_style": "threshold_trade_not_pure_cut",
    }
