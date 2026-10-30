"""采购侧方案推演：单供 / 凑满减(含跨省补贴) / 拆单。

预算不是必填项。若人类在对话里自愿提到「预算紧/宽裕」，可作 soft_budget
或 posture 提示用于排序与标签，但绝不向供应商泄露，也绝不阻塞出方案。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agents.supplier_common.promo import settle_quote_economics

_ROOT = Path(__file__).resolve().parents[1]


def _load_policy(agent_id: str) -> dict[str, Any]:
    folder = agent_id.replace("-", "_")
    for path in (
        _ROOT / "agents" / agent_id / "policy.yaml",
        _ROOT / "agents" / folder / "policy.yaml",
    ):
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
    return {}


def _payload(q: dict[str, Any]) -> dict[str, Any]:
    return q.get("payload") if isinstance(q.get("payload"), dict) else (q if isinstance(q, dict) else {})


def _freight_of(pay: dict[str, Any]) -> float | None:
    if pay.get("shipping_cost") is not None:
        try:
            return float(pay["shipping_cost"])
        except (TypeError, ValueError):
            return None
    if pay.get("freight_amount") is not None:
        try:
            return float(pay["freight_amount"])
        except (TypeError, ValueError):
            return None
    fr = pay.get("freight")
    if isinstance(fr, dict) and fr.get("amount") is not None:
        try:
            return float(fr["amount"])
        except (TypeError, ValueError):
            return None
    return None


def _scale_freight(base: float | None, *, from_qty: int, to_qty: int) -> float | None:
    if base is None or from_qty <= 0:
        return base
    return round(float(base) * (to_qty / from_qty), 2)


def _supplier_row(quotes: list[dict[str, Any]], agent_id: str) -> dict[str, Any] | None:
    for q in quotes:
        pay = _payload(q)
        if pay.get("supplier_agent_id") == agent_id:
            return pay
    return None


def _estimate(
    *,
    agent_id: str,
    qty: int,
    unit_price: float,
    base_freight: float | None,
    base_qty: int,
    dest_province: str,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pol = policy if policy is not None else _load_policy(agent_id)
    freight = _scale_freight(base_freight, from_qty=base_qty, to_qty=qty)
    econ = settle_quote_economics(
        pol,
        qty=qty,
        unit_price=unit_price,
        freight=freight,
        rfq_payload={"dest_province": dest_province, "destination": {"province": dest_province}},
    )
    avail = int(pol.get("available_quantity") or 10**9)
    return {
        "supplier_agent_id": agent_id,
        "quantity": qty,
        "unit_price": unit_price,
        "available_quantity": avail,
        "can_fulfill": qty <= avail,
        "economics": econ,
        "estimated_tco": econ.get("tco"),
        "uncertain": bool((econ.get("cross_province_subsidy") or {}).get("uncertain") and (econ.get("cross_province_subsidy") or {}).get("applied")),
        "policy_hints": econ.get("policy_hints") or [],
    }


def plan_procurement_schemes(
    *,
    quotes: list[dict[str, Any]],
    base_qty: int,
    dest_province: str = "河北",
    soft_budget: float | None = None,
    budget_posture: str | None = None,
) -> dict[str, Any]:
    """生成多方案。soft_budget / budget_posture 均可空。

    budget_posture: ample | tight | None
    """
    base_qty = max(int(base_qty or 1), 1)
    posture = (budget_posture or "").strip().lower() or None
    if soft_budget is not None and posture is None:
        # 有数字但未声明松紧时，不擅自定性，只做标签
        posture = None

    suppliers: list[dict[str, Any]] = []
    for q in quotes:
        pay = _payload(q)
        sid = pay.get("supplier_agent_id")
        unit = pay.get("unit_price")
        if not sid or unit is None:
            continue
        qty0 = int((pay.get("product") or {}).get("quantity") or base_qty)
        pol = _load_policy(str(sid))
        # 议价回执可能已带 promo_settlement
        freight = _freight_of(pay)
        row = _estimate(
            agent_id=str(sid),
            qty=base_qty,
            unit_price=float(unit),
            base_freight=freight,
            base_qty=qty0 if qty0 > 0 else base_qty,
            dest_province=dest_province,
            policy=pol,
        )
        # 凑满减目标量（不超过可售库存）
        gap = (row["economics"] or {}).get("next_tier")
        reach = None
        avail = int(pol.get("available_quantity") or 10**9)
        if gap and gap.get("target_qty"):
            tgt = min(int(gap["target_qty"]), avail)
            if tgt > base_qty:
                reach = _estimate(
                    agent_id=str(sid),
                    qty=tgt,
                    unit_price=float(unit),
                    base_freight=freight,
                    base_qty=qty0 if qty0 > 0 else base_qty,
                    dest_province=dest_province,
                    policy=pol,
                )
        # 山西跨省补贴门槛：在库存允许范围内冲量；冲不到则只留说明
        sub_reach = None
        cfg = (pol.get("promotions") or {}).get("cross_province_subsidy") if isinstance(pol.get("promotions"), dict) else None
        if isinstance(cfg, dict) and cfg.get("enabled"):
            min_q = int(cfg.get("min_qty") or base_qty)
            tgt = min(max(base_qty, min_q), avail)
            if tgt >= min_q and tgt != base_qty:
                sub_reach = _estimate(
                    agent_id=str(sid),
                    qty=tgt,
                    unit_price=float(unit),
                    base_freight=freight,
                    base_qty=qty0 if qty0 > 0 else base_qty,
                    dest_province=dest_province,
                    policy=pol,
                )
            elif avail < min_q:
                # 库存不足以申请补贴 → 策略讨论点（拆单/改量）
                s_note = {
                    "blocked_by_inventory": True,
                    "min_qty": min_q,
                    "available_quantity": avail,
                    "hint": f"跨省补贴需满 {min_q} 件，但可售仅 {avail}，需拆单或改采才能讨论该政策",
                }
                row = dict(row)
                row["subsidy_blocked"] = s_note

        suppliers.append(
            {
                "supplier_agent_id": str(sid),
                "as_is": row,
                "reach_full_reduction": reach,
                "reach_cross_province": sub_reach,
                "policy": {
                    "merchant": (pol.get("merchant") or {}).get("trade_name"),
                    "province": (pol.get("merchant") or {}).get("province"),
                    "available_quantity": pol.get("available_quantity"),
                },
            }
        )

    schemes: list[dict[str, Any]] = []

    # S1：单供 · 维持现量
    for s in suppliers:
        row = s["as_is"]
        if not row.get("can_fulfill"):
            continue
        schemes.append(
            {
                "scheme_id": f"S1-{row['supplier_agent_id']}",
                "kind": "single_as_is",
                "title": f"单供维持现量 · {row['supplier_agent_id']}",
                "summary": "不改采购量；挂牌价不变，只吃已触发的满减/单品折扣/补贴（若有）",
                "lines": [{"supplier_agent_id": row["supplier_agent_id"], "quantity": row["quantity"], "unit_price": row["unit_price"]}],
                "estimated_tco": row.get("estimated_tco"),
                "uncertain": row.get("uncertain"),
                "fit": "ample_or_neutral",
                "detail": row,
            }
        )

    # S2：单供 · 凑满减 / 冲跨省补贴
    for s in suppliers:
        for key, label in (
            ("reach_full_reduction", "凑满减加量"),
            ("reach_cross_province", "冲跨省补贴门槛"),
        ):
            row = s.get(key)
            if not row or not row.get("can_fulfill"):
                continue
            if row["quantity"] == base_qty and key == "reach_cross_province":
                # 现量已达门槛则并入 S1 叙述即可
                if (row.get("economics") or {}).get("cross_province_subsidy", {}).get("applied"):
                    pass
                else:
                    continue
            schemes.append(
                {
                    "scheme_id": f"S2-{key}-{row['supplier_agent_id']}",
                    "kind": "single_reach_promo",
                    "title": f"{label} · {row['supplier_agent_id']}",
                    "summary": (
                        f"加量至 {row['quantity']} 件换活动条件；"
                        f"适合预算相对宽裕、能接受多采一点的路径"
                        + ("；跨省补贴须审核、结果不确定" if key == "reach_cross_province" else "")
                    ),
                    "lines": [
                        {
                            "supplier_agent_id": row["supplier_agent_id"],
                            "quantity": row["quantity"],
                            "unit_price": row["unit_price"],
                        }
                    ],
                    "estimated_tco": row.get("estimated_tco"),
                    "uncertain": bool(row.get("uncertain") or key == "reach_cross_province"),
                    "fit": "ample",
                    "detail": row,
                }
            )

    # S3：拆单 — 库存不足或预算偏紧时，把量拆到两家
    fulfillable = [s for s in suppliers if s["as_is"].get("can_fulfill")]
    scarce = [s for s in suppliers if not s["as_is"].get("can_fulfill")]
    # 经典路径：C 库存紧 → 能供多少拿多少，其余给单价更低的河北厂
    c = next((s for s in suppliers if s["supplier_agent_id"] == "supplier-c"), None)
    others = [s for s in suppliers if s["supplier_agent_id"] != "supplier-c" and s["as_is"].get("can_fulfill")]
    if c and others:
        avail_c = int(c["as_is"].get("available_quantity") or 0)
        take_c = min(base_qty, avail_c) if avail_c > 0 else 0
        rest = base_qty - take_c
        if take_c > 0 and rest > 0:
            best_other = min(others, key=lambda s: float(s["as_is"].get("estimated_tco") or 1e18))
            line_c = _estimate(
                agent_id="supplier-c",
                qty=take_c,
                unit_price=float(c["as_is"]["unit_price"]),
                base_freight=_freight_of(_supplier_row(quotes, "supplier-c") or {}),
                base_qty=int((_supplier_row(quotes, "supplier-c") or {}).get("product", {}).get("quantity") or base_qty),
                dest_province=dest_province,
            )
            other_id = best_other["supplier_agent_id"]
            line_o = _estimate(
                agent_id=other_id,
                qty=rest,
                unit_price=float(best_other["as_is"]["unit_price"]),
                base_freight=_freight_of(_supplier_row(quotes, other_id) or {}),
                base_qty=int((_supplier_row(quotes, other_id) or {}).get("product", {}).get("quantity") or base_qty),
                dest_province=dest_province,
            )
            tco = round(float(line_c.get("estimated_tco") or 0) + float(line_o.get("estimated_tco") or 0), 2)
            schemes.append(
                {
                    "scheme_id": f"S3-split-c-{other_id}",
                    "kind": "split_order",
                    "title": f"拆单 · 山西{take_c}+{other_id}×{rest}",
                    "summary": (
                        "按库存与成本拆成两张单：山西有多少拿多少（可讨论跨省补贴），"
                        "缺口由河北侧补齐。预算紧时不必硬冲满减门槛。"
                    ),
                    "lines": [
                        {"supplier_agent_id": "supplier-c", "quantity": take_c, "unit_price": line_c["unit_price"]},
                        {"supplier_agent_id": other_id, "quantity": rest, "unit_price": line_o["unit_price"]},
                    ],
                    "estimated_tco": tco,
                    "uncertain": bool(line_c.get("uncertain")),
                    "fit": "tight",
                    "detail": {"parts": [line_c, line_o]},
                }
            )

    # 两家河北拆分（各一半）——预算紧、不想加量时的备选
    hebei = [s for s in fulfillable if (s.get("policy") or {}).get("province") == "河北"]
    if len(hebei) >= 2 and base_qty >= 2:
        a, b = hebei[0], hebei[1]
        q1 = base_qty // 2
        q2 = base_qty - q1
        la = _estimate(
            agent_id=a["supplier_agent_id"],
            qty=q1,
            unit_price=float(a["as_is"]["unit_price"]),
            base_freight=_freight_of(_supplier_row(quotes, a["supplier_agent_id"]) or {}),
            base_qty=base_qty,
            dest_province=dest_province,
        )
        lb = _estimate(
            agent_id=b["supplier_agent_id"],
            qty=q2,
            unit_price=float(b["as_is"]["unit_price"]),
            base_freight=_freight_of(_supplier_row(quotes, b["supplier_agent_id"]) or {}),
            base_qty=base_qty,
            dest_province=dest_province,
        )
        schemes.append(
            {
                "scheme_id": f"S3-split-{a['supplier_agent_id']}-{b['supplier_agent_id']}",
                "kind": "split_order",
                "title": f"拆单 · {a['supplier_agent_id']}×{q1}+{b['supplier_agent_id']}×{q2}",
                "summary": "两家河北厂拆量，避开跨省不确定性，也不强行加量冲活动",
                "lines": [
                    {"supplier_agent_id": a["supplier_agent_id"], "quantity": q1, "unit_price": la["unit_price"]},
                    {"supplier_agent_id": b["supplier_agent_id"], "quantity": q2, "unit_price": lb["unit_price"]},
                ],
                "estimated_tco": round(float(la.get("estimated_tco") or 0) + float(lb.get("estimated_tco") or 0), 2),
                "uncertain": False,
                "fit": "tight",
                "detail": {"parts": [la, lb]},
            }
        )

    # 标签：相对软预算 / 姿态
    for sch in schemes:
        tco = sch.get("estimated_tco")
        tags: list[str] = []
        if soft_budget is not None and tco is not None:
            tags.append("within_soft_budget" if float(tco) <= float(soft_budget) else "over_soft_budget")
        if posture == "ample" and sch.get("fit") == "ample":
            tags.append("recommended_for_ample_budget")
        if posture == "tight" and sch.get("fit") == "tight":
            tags.append("recommended_for_tight_budget")
        if sch.get("uncertain"):
            tags.append("has_uncertainty")
        sch["tags"] = tags

    def sort_key(sch: dict[str, Any]) -> tuple:
        tco = float(sch["estimated_tco"]) if sch.get("estimated_tco") is not None else 1e18
        # 预算紧：拆单优先；宽裕：满减/补贴优先；默认按 TCO
        prefer = 1
        if posture == "tight" and sch.get("kind") == "split_order":
            prefer = 0
        if posture == "ample" and sch.get("kind") == "single_reach_promo":
            prefer = 0
        uncertain_penalty = 1 if sch.get("uncertain") and posture == "tight" else 0
        return (prefer, uncertain_penalty, tco)

    schemes_sorted = sorted(schemes, key=sort_key)

    return {
        "base_qty": base_qty,
        "dest_province": dest_province,
        "soft_budget": soft_budget,
        "budget_posture": posture,
        "budget_required": False,
        "note": (
            "预算不是必填。智能体默认给出多条可执行方案："
            "维持现量、凑满减/冲补贴、拆单分采。"
            "预算宽裕可优先看活动门槛；偏紧可看拆单。"
            "山西跨省补贴带审核不确定性。"
        ),
        "supplier_snapshots": suppliers,
        "schemes": schemes_sorted,
        "recommended_scheme_id": schemes_sorted[0]["scheme_id"] if schemes_sorted else None,
    }
