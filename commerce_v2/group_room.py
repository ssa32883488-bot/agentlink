# -*- coding: utf-8 -*-
"""组群竞价聊天室：入群 ticker、群内发言时序、最佳/拆分方案。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from commerce_v2.catalog import SUPPLIERS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_room(*, host: str, members: list[str], brief: dict[str, Any]) -> dict[str, Any]:
    seats = []
    for mid in members:
        role = "logistics" if mid == "logistics" else ("host" if mid == host else "supplier")
        seats.append({"id": mid, "role": role, "status": "invited", "title": _title(mid)})
    return {
        "status": "connecting",
        "host": host,
        "transport": None,
        "group_id": None,
        "members": seats,
        "ticker": [],
        "messages": [],
        "bids": [],
        "logistics_scheme": None,
        "summary": None,
        "brief": {
            "name": brief.get("name"),
            "sku": brief.get("sku"),
            "qty": brief.get("qty"),
            "items": brief.get("items") or [],
            "multi": bool(brief.get("multi")),
            "query": brief.get("rewritten_query") or brief.get("raw") or "",
        },
        "updated_at": _now(),
    }


def _title(agent_id: str) -> str:
    if agent_id == "logistics":
        return "采联物流智能体"
    if agent_id.startswith("buyer"):
        return f"采购主持·{agent_id}"
    meta = SUPPLIERS.get(agent_id) or {}
    return meta.get("title") or agent_id


def tick(room: dict[str, Any], text: str, *, kind: str = "info", agent_id: str | None = None) -> None:
    room.setdefault("ticker", []).append(
        {"t": _now(), "text": text, "kind": kind, "agent_id": agent_id}
    )
    room["updated_at"] = _now()


def say(
    room: dict[str, Any],
    *,
    agent_id: str,
    content: str,
    role: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    if role is None:
        if agent_id == "logistics":
            role = "logistics"
        elif str(agent_id).startswith("buyer"):
            role = "host"
        elif str(agent_id).startswith("supplier"):
            role = "supplier"
        else:
            role = "system"
    room.setdefault("messages", []).append(
        {
            "t": _now(),
            "agent_id": agent_id,
            "role": role,
            "name": _title(agent_id),
            "content": content,
            "meta": meta or {},
        }
    )
    room["updated_at"] = _now()


def set_member_status(room: dict[str, Any], agent_id: str, status: str) -> None:
    for m in room.get("members") or []:
        if m.get("id") == agent_id:
            m["status"] = status
            break


def build_summary(
    *,
    brief: dict[str, Any],
    bids: list[dict[str, Any]],
    logistics_scheme: dict[str, Any] | None,
    demand_text: str = "",
) -> dict[str, Any]:
    """主持汇总：多品必须全覆盖；优先「全量组合/拆分」，单品才推最优整单。"""
    from commerce_v2.demand_items import bid_matches_line, enrich_brief_items, extract_line_items

    freight = float((logistics_scheme or {}).get("shipping_cost") or (logistics_scheme or {}).get("fee") or 0)
    demand = demand_text or str(brief.get("rewritten_query") or brief.get("raw") or "")
    brief = enrich_brief_items(dict(brief or {}), text=demand)
    want_lines = list(brief.get("items") or []) or extract_line_items(demand)
    multi = len(want_lines) >= 2

    ranked = sorted(
        [b for b in bids if b.get("unit_price") is not None],
        key=lambda b: float(b.get("goods_total") or (float(b.get("unit_price") or 0) * float(b.get("qty") or brief.get("qty") or 0))),
    )
    best = ranked[0] if ranked else None
    plans: list[dict[str, Any]] = []
    missing: list[str] = []

    # 多品：按行取最优价，必须覆盖全部需求行
    if multi:
        combo = _best_combo_lines(want_lines, bids)
        covered = {str(x.get("line_key") or x.get("sku") or x.get("name")) for x in combo}
        for line in want_lines:
            key = str(line.get("prefix") or line.get("sku") or line.get("name"))
            if key not in covered and not any(bid_matches_line(x, line) for x in combo):
                # 也按 name 比对
                if not any(
                    str(x.get("name") or "").find(str(line.get("name") or "")[:2]) >= 0 for x in combo
                ):
                    missing.append(str(line.get("name") or line.get("sku")))
        if len(combo) >= 2 and not missing:
            goods = sum(float(x.get("goods_total") or 0) for x in combo)
            split_freight = round(freight * len(combo), 2) if freight else 0
            names = " + ".join(f"{x.get('name')}←{x.get('supplier_id')}" for x in combo)
            plans.append(
                {
                    "id": "plan_split",
                    "label": f"全量覆盖 · {len(combo)} 品拆单 · {names}",
                    "kind": "split",
                    "lines": combo,
                    "freight": split_freight,
                    "total": round(goods + split_freight, 2),
                    "primary": True,
                    "covers_all": True,
                }
            )
        elif len(combo) >= 1:
            # 有报价但未盖全：仍给出已覆盖部分，并标记缺口
            goods = sum(float(x.get("goods_total") or 0) for x in combo)
            split_freight = round(freight * max(len(combo), 1), 2) if freight else 0
            plans.append(
                {
                    "id": "plan_split",
                    "label": f"部分覆盖 · 已报 {len(combo)}/{len(want_lines)} 品（缺：{'、'.join(missing) or '—'}）",
                    "kind": "split",
                    "lines": combo,
                    "freight": split_freight,
                    "total": round(goods + split_freight, 2),
                    "primary": True,
                    "covers_all": False,
                    "missing": missing,
                }
            )

        # 若单一供应能覆盖全部行，追加整包方案
        one_pack = _single_supplier_cover(want_lines, bids)
        if one_pack:
            goods = sum(float(x.get("goods_total") or 0) for x in one_pack)
            sid = one_pack[0].get("supplier_id")
            plans.append(
                {
                    "id": "plan_best",
                    "label": f"单家全包 · {sid} · {len(one_pack)} 品",
                    "kind": "single",
                    "lines": one_pack,
                    "freight": freight,
                    "total": round(goods + freight, 2),
                    "primary": False,
                    "covers_all": True,
                }
            )
    else:
        if best:
            goods = float(best.get("goods_total") or 0)
            plans.append(
                {
                    "id": "plan_best",
                    "label": f"最优整单 · {best.get('supplier_agent_id')} @ {best.get('unit_price')}",
                    "kind": "single",
                    "lines": [
                        {
                            "supplier_id": best.get("supplier_agent_id"),
                            "sku": best.get("sku") or brief.get("sku"),
                            "name": best.get("name") or brief.get("name"),
                            "qty": best.get("qty") or brief.get("qty"),
                            "unit_price": best.get("unit_price"),
                            "goods_total": goods,
                        }
                    ],
                    "freight": freight,
                    "total": round(goods + freight, 2),
                    "primary": True,
                    "covers_all": True,
                }
            )

    narrative = []
    if multi:
        narrative.append(
            "需求行："
            + "；".join(f"{x.get('name')}×{x.get('qty')}{x.get('unit') or ''}" for x in want_lines)
            + "。"
        )
        if missing:
            narrative.append(f"⚠ 尚未覆盖：{'、'.join(missing)}，请补选有货供应或续跑报价。")
        elif any(p.get("covers_all") for p in plans):
            narrative.append("全部品类均已拿到报价，可拆单一次下齐。")
    elif best:
        narrative.append(
            f"货价最优：{best.get('supplier_agent_id')} · {best.get('name')} "
            f"单价 {best.get('unit_price')}，货款 {best.get('goods_total')}。"
        )
    if logistics_scheme:
        narrative.append(
            f"物流方案：{logistics_scheme.get('mode') or logistics_scheme.get('carrier') or '标准运力'}，"
            f"运费约 {freight}，ETA {logistics_scheme.get('eta_days') or '—'} 天。"
        )
    return {
        "ranked": ranked,
        "best": best,
        "plans": plans,
        "freight": freight,
        "narrative": " ".join(narrative) or "暂无可用方案。",
        "split_available": any(p.get("kind") == "split" for p in plans),
        "want_lines": want_lines,
        "missing": missing,
        "covers_all": bool(plans) and all(p.get("covers_all") for p in plans if p.get("primary")),
    }


def _best_combo_lines(want_lines: list[dict[str, Any]], bids: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from commerce_v2.demand_items import bid_matches_line

    out: list[dict[str, Any]] = []
    used_bid_idx: set[int] = set()
    for line in want_lines:
        matched: list[tuple[int, dict[str, Any]]] = []
        for i, b in enumerate(bids):
            if i in used_bid_idx:
                continue
            if bid_matches_line(b, line):
                matched.append((i, b))
        if not matched:
            continue
        i, b = min(matched, key=lambda t: float(t[1].get("unit_price") or 1e18))
        used_bid_idx.add(i)
        qty = int(line.get("qty") or b.get("qty") or 1)
        unit_price = float(b.get("unit_price") or 0)
        goods = float(b.get("goods_total") or round(unit_price * qty, 2))
        out.append(
            {
                "supplier_id": b.get("supplier_agent_id"),
                "sku": b.get("sku") or line.get("sku"),
                "name": b.get("name") or line.get("name"),
                "qty": qty,
                "unit_price": unit_price,
                "goods_total": goods,
                "line_key": str(line.get("prefix") or line.get("sku") or line.get("name")),
            }
        )
    return out


def _single_supplier_cover(want_lines: list[dict[str, Any]], bids: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    from commerce_v2.demand_items import bid_matches_line

    by_sid: dict[str, list[dict[str, Any]]] = {}
    for b in bids:
        sid = str(b.get("supplier_agent_id") or "")
        if sid:
            by_sid.setdefault(sid, []).append(b)
    for sid, sbids in by_sid.items():
        lines: list[dict[str, Any]] = []
        ok = True
        for line in want_lines:
            hits = [b for b in sbids if bid_matches_line(b, line)]
            if not hits:
                ok = False
                break
            b = min(hits, key=lambda x: float(x.get("unit_price") or 1e18))
            qty = int(line.get("qty") or b.get("qty") or 1)
            unit_price = float(b.get("unit_price") or 0)
            lines.append(
                {
                    "supplier_id": sid,
                    "sku": b.get("sku") or line.get("sku"),
                    "name": b.get("name") or line.get("name"),
                    "qty": qty,
                    "unit_price": unit_price,
                    "goods_total": float(b.get("goods_total") or round(unit_price * qty, 2)),
                }
            )
        if ok and len(lines) == len(want_lines):
            return lines
    return None
