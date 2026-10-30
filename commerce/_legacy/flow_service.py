"""指导书 10 步主路径编排：发现→HITL→询价→对比三选→议价/竞价→物流合同→双边确认。"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from agentlink_runtime.aip_client_util import aip_start_structured
from agentlink_runtime.aip_payload import wrap_business
from agents.buyer_a.graph import build_order_draft, compare_quotes
from commerce.scheme_planner import plan_procurement_schemes
from commerce import procurement_case as pc
from commerce.discovery import discover_suppliers
from commerce.hitl_gate import make_hitl, narrative_line
from commerce.merchant import buyer_destination
from commerce.progress import report
from commerce.rfq_bridge import SUPPLIER_MAP


def _buyer_agent_id() -> str:
    return (os.getenv("BUYER_AGENT_ID") or "buyer-a").strip()


def LEADER_AIC() -> str:
    aid = _buyer_agent_id()
    if aid == "buyer-b":
        return os.getenv("BUYER_B_AIC") or os.getenv("BUYER_A_AIC") or "buyer-b-local-aic"
    return os.getenv("BUYER_A_AIC") or "buyer-a-local-aic"


def _supplier_meta(agent_id: str) -> dict[str, str]:
    meta = SUPPLIER_MAP.get(agent_id)
    if not meta:
        raise ValueError(f"未知供应商 {agent_id}")
    return meta


def create_from_brief(
    *,
    product_name: str = "重型脚轮",
    quantity: int = 500,
    rated_load_kg_min: int = 300,
    note: str = "",
    lines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    norm_lines: list[dict[str, Any]] = []
    for row in lines or []:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or row.get("product_name") or "").strip()
        name = str(row.get("name") or sku).strip()
        if not sku and not name:
            continue
        try:
            qty = float(row.get("qty") if row.get("qty") is not None else row.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1.0
        norm_lines.append(
            {
                "sku": sku or name,
                "name": name or sku,
                "qty": qty,
                "unit": str(row.get("unit") or "件"),
                "specs": dict(row.get("specs") or {}),
            }
        )
    # 组合需求：数量只存在 lines[*].qty；brief.quantity 取首行（禁止 500+200=700 串总量）
    label = product_name
    qty = quantity
    display = None
    if norm_lines:
        display = " + ".join(
            f"{x.get('name') or x.get('sku')}×{int(x.get('qty') or 1)}" for x in norm_lines
        )
        label = display
        qty = int(float(norm_lines[0].get("qty") or quantity or 1))
    brief = {
        "product_name": label,
        "quantity": qty,
        "specifications": {"rated_load_kg_min": rated_load_kg_min},
        "currency": "CNY",
        "note": note,
        "purchase_request_id": f"pr-{uuid4().hex[:8]}",
        "version": 1,
        "human_approval_status": "approved",
        "quality_requirements": ["提供批次质检资料"],
        "delivery": {"deadline": "2026-11-15", "destination_ref": "addr-buyer-1"},
    }
    if norm_lines:
        brief["lines"] = norm_lines
        brief["combo"] = True
        if display:
            brief["display_label"] = display
    return pc.create_case(brief=brief)


async def step_discover(
    case_id: str,
    query: str | None = None,
    *,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    case = pc.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    pc.transition(case_id, "DISCOVERING", event="discover_start")
    product = (case.get("brief") or {}).get("product_name") or "工业原料"
    report(f"采购案 {case_id}：开始发现供应商…", phase="flow")
    q = query or (
        f"工业原料供应商 报价 agentlink.supplier；需要供应「{product}」的采联供应商智能体"
    )
    discovered = await discover_suppliers(q, limit=5, bypass_cache=bypass_cache)
    report(
        f"发现完成 · 来源 {(discovered.get('source') or '?')} · 候选 {len(discovered.get('candidates') or [])} 家",
        phase="flow",
    )
    case = pc.transition(
        case_id,
        "SHORTLIST_PENDING",
        event="discover_done",
        patch={
            "candidates": discovered["candidates"],
            "discovery_meta": {
                "source": discovered["source"],
                "query": discovered["query"],
                "platform_error": discovered.get("platform_error"),
                "discovery_url": discovered.get("discovery_url"),
                "degrade": discovered.get("degrade"),
                "degrade_reason": discovered.get("degrade_reason"),
                "elapsed_ms": discovered.get("elapsed_ms"),
                "cache_hit": discovered.get("cache_hit"),
            },
            "hitl_pending": make_hitl(
                "confirm_shortlist",
                "请确认与哪些供应商发起 AIP 询价（至少选 1 家）",
                options=["approve", "edit", "reject"],
                extra={
                    "source_label": (discovered.get("source") or ""),
                    "degrade": bool(discovered.get("degrade")),
                    "degrade_reason": discovered.get("degrade_reason"),
                },
            ),
            "shortlist_confirmed": False,
            "shortlist": [],
            "rfq_fingerprint": None,
            "voided": False,
        },
    )
    report(narrative_line(case.get("hitl_pending")), phase="hitl")
    return case


def step_confirm_shortlist(case_id: str, agent_ids: list[str]) -> dict[str, Any]:
    case = pc.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    if case.get("voided"):
        raise ValueError("案件已作废，不可再确认短名单")
    ids = [a for a in agent_ids if a in SUPPLIER_MAP]
    if not ids:
        raise ValueError("shortlist 为空或无效")
    # 幂等：已确认且短名单一致 → 直接返回
    if case.get("shortlist_confirmed") and case["state"] in ("SOURCING", "COMPARE_PENDING"):
        prev = [p.get("agent_id") for p in (case.get("shortlist") or [])]
        if prev == ids:
            return case
    if case["state"] != "SHORTLIST_PENDING":
        raise ValueError(f"当前状态 {case['state']} 不能确认 shortlist")
    cand_map = {c["agent_id"]: c for c in case.get("candidates") or []}
    shortlist = []
    for i in ids:
        if i in cand_map:
            shortlist.append(cand_map[i])
        else:
            meta = _supplier_meta(i)
            shortlist.append(
                {
                    "agent_id": i,
                    "aic": meta["aic"],
                    "name": i,
                    "endpoint": meta["url"],
                    "source": "manual",
                }
            )
    return pc.transition(
        case_id,
        "SOURCING",
        event="shortlist_confirmed",
        patch={
            "shortlist": shortlist,
            "shortlist_confirmed": True,
            "hitl_pending": None,
            "rfq_fingerprint": None,
        },
    )


def step_hitl_decide(
    case_id: str,
    decision: str,
    *,
    agent_ids: list[str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    """HITL 四态：approve / edit / reject / respond。"""
    case = pc.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    decision = (decision or "").strip().lower()
    if decision not in ("approve", "edit", "reject", "respond"):
        raise ValueError("decision 须为 approve|edit|reject|respond")
    hitl = case.get("hitl_pending") or {}
    gate = hitl.get("gate") or ""
    audit_extra = {
        "at": datetime.now(timezone.utc).isoformat(),
        "event": f"hitl_{decision}",
        "gate": gate,
        "note": note,
        "state": case["state"],
    }

    if decision == "reject":
        # 作废：清副作用标记，禁止后续询价/下单；不重复询价
        return pc.transition(
            case_id,
            "EXCEPTION",
            event="hitl_reject",
            patch={
                "voided": True,
                "shortlist_confirmed": False,
                "hitl_pending": None,
                "reject_note": note or "用户拒绝门禁",
                "audit": (case.get("audit") or []) + [audit_extra],
            },
        )

    if decision == "edit":
        if gate == "confirm_shortlist":
            # 回到短名单待确认，允许改选；不触发询价
            ids = [a for a in (agent_ids or []) if a in SUPPLIER_MAP]
            patch: dict[str, Any] = {
                "shortlist_confirmed": False,
                "rfq_fingerprint": None,
                "hitl_pending": make_hitl(
                    "confirm_shortlist",
                    "已进入改选：请重新确认短名单后再询价",
                    options=["approve", "edit", "reject"],
                ),
                "audit": (case.get("audit") or []) + [audit_extra],
            }
            if ids:
                cand_map = {c["agent_id"]: c for c in case.get("candidates") or []}
                patch["shortlist"] = [
                    cand_map[i]
                    if i in cand_map
                    else {
                        "agent_id": i,
                        "aic": _supplier_meta(i)["aic"],
                        "name": i,
                        "endpoint": _supplier_meta(i)["url"],
                        "source": "manual",
                    }
                    for i in ids
                ]
            if case["state"] != "SHORTLIST_PENDING":
                return pc.transition(case_id, "SHORTLIST_PENDING", event="hitl_edit", patch=patch)
            return pc.update_case(case_id, **patch)
        # 其他门禁 edit：保持状态，刷新提示
        refreshed = make_hitl(
            gate or "compare_decide",
            note or hitl.get("prompt") or "请按新参数重新决策",
            options=list(hitl.get("options") or []),
        )
        return pc.update_case(
            case_id,
            hitl_pending=refreshed,
            audit=(case.get("audit") or []) + [audit_extra],
        )

    if decision == "respond":
        return pc.update_case(
            case_id,
            hitl_pending={
                **(hitl if isinstance(hitl, dict) else {}),
                "status": "noted",
                "user_response": note,
                "next_hint": note or hitl.get("next_hint"),
            },
            audit=(case.get("audit") or []) + [audit_extra],
        )

    # approve：仅标记门禁已批，具体业务仍由对应 step_* 执行（避免重复副作用）
    if not hitl:
        raise ValueError("当前无待确认门禁")
    return pc.update_case(
        case_id,
        hitl_pending={**hitl, "status": "approved", "approved_at": audit_extra["at"]},
        audit=(case.get("audit") or []) + [audit_extra],
    )


async def step_rfq(case_id: str) -> dict[str, Any]:
    case = pc.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    if case.get("voided"):
        raise ValueError("案件已作废，不可询价")
    if not case.get("shortlist_confirmed"):
        raise ValueError("须先 HITL 确认 shortlist")
    fp = ",".join(sorted(p.get("agent_id") or "" for p in (case.get("shortlist") or [])))
    # 幂等：同 shortlist 指纹已询过且在对比态 → 不重复发 AIP
    if (
        case["state"] == "COMPARE_PENDING"
        and case.get("rfq_fingerprint") == fp
        and case.get("quotes")
    ):
        report(f"询价幂等命中 · 复用已有报价 · fingerprint={fp}", phase="aip")
        return case
    if case["state"] not in ("SOURCING", "COMPARE_PENDING"):
        # 允许从 SHORTLIST 确认后立即询价
        if case["state"] != "SOURCING":
            raise ValueError(f"状态 {case['state']} 不可询价")
    brief = case["brief"]
    deadline = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    quotes: list[dict[str, Any]] = []
    errors: list[str] = []
    n_partners = len(case.get("shortlist") or [])
    report(f"Leader 并行向 {n_partners} 家 Partner 发起 AIP 询价", phase="aip")
    for partner in case["shortlist"]:
        meta = _supplier_meta(partner["agent_id"])
        # 短名单可能仍带平台旧 AIC；出站身份必须以本域证书 CN（env）为准
        aic = meta["aic"]
        url = meta["url"] or partner.get("endpoint")
        label = partner.get("name") or partner["agent_id"]
        report(f"经 AIP 向「{label}」发送询价请求…", phase="aip")
        specs = dict(brief.get("specifications") or {})
        # 供应商B（定制MOQ）需要 material/color；流程默认补齐以免 awaiting-input
        if partner["agent_id"] == "supplier-b":
            specs.setdefault("material", "steel")
            specs.setdefault("color", "black")
        dest = buyer_destination(_buyer_agent_id())
        dest_body = {"postal_code": dest["postal_code"], "city": dest.get("city"), "address": dest.get("address")}
        envelope = wrap_business(
            "agentlink.quote_request",
            case_id,
            {
                "purchase_request_id": brief["purchase_request_id"],
                "version": 1,
                "product_name": brief["product_name"],
                "specifications": specs,
                "quantity": max(int(brief["quantity"]), 200 if partner["agent_id"] == "supplier-b" else 1),
                "currency": "CNY",
                "tax_included_required": True,
                "delivery_deadline": (brief.get("delivery") or {}).get("deadline"),
                "quality_requirements": brief.get("quality_requirements") or [],
                "quote_deadline": deadline,
                "need_bargain_room": False,
                "need_freight": False,
                "destination": dest_body,
                "postal_code": dest_body["postal_code"],
            },
        )
        try:
            out = await aip_start_structured(
                partner_url=url,
                leader_aic=LEADER_AIC(),
                partner_aic=aic,
                session_id=f"flow-rfq-{case_id}-{partner['agent_id']}",
                envelope=envelope,
                local_agent_id=_buyer_agent_id(),
            )
            if out.get("envelope"):
                env = out["envelope"]
                # 标注供应商
                pay = env.setdefault("payload", {})
                pay.setdefault("supplier_agent_id", partner["agent_id"])
                quotes.append(env)
                unit = (pay.get("unit_price") if isinstance(pay, dict) else None) or "?"
                report(f"「{label}」已回报价 · 单价 ¥{unit} · {out.get('state')}", phase="aip")
            else:
                errors.append(f"{partner['agent_id']}: {out.get('message') or out.get('state')}")
                report(f"「{label}」询价未完成：{out.get('message') or out.get('state')}", phase="aip")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{partner['agent_id']}: {exc}")
            report(f"「{label}」询价失败：{exc}", phase="aip")

    comparison = compare_quotes(quotes)
    # 扩展对比字段
    for row in comparison.get("quotes") or []:
        for q in quotes:
            p = q.get("payload") or {}
            if p.get("supplier_agent_id") == row.get("supplier_agent_id") or p.get("quote_id") == row.get("quote_id"):
                row["bargain_room"] = p.get("bargain_room")
                row["valid_until"] = p.get("valid_until")
                row["available_quantity"] = p.get("available_quantity")
    case = pc.transition(
        case_id,
        "COMPARE_PENDING",
        event="rfq_done",
        patch={
            "quotes": quotes,
            "comparison": comparison,
            "rfq_errors": errors,
            "rfq_fingerprint": fp,
            "hitl_pending": make_hitl(
                "compare_decide",
                f"已收到 {len(quotes)} 家 Partner 报价，请三选一决策",
                options=["order", "negotiate", "auction"],
            ),
        },
    )
    report(narrative_line(case.get("hitl_pending")), phase="hitl")
    return case


def _narrow_brief_for_order(
    brief: dict[str, Any],
    *,
    sku: str | None = None,
    quote_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """下单时把组合 brief 收成单行，避免数量/品名串台。"""
    try:
        from agents.supplier_common.catalog_price import normalize_sku
    except Exception:  # noqa: BLE001
        def normalize_sku(text: str | None) -> str | None:  # type: ignore
            return str(text).strip().upper() if text else None

    pay = quote_payload or {}
    want = normalize_sku(sku) or normalize_sku(str(pay.get("sku") or pay.get("product_name") or ""))
    lines = [x for x in (brief.get("lines") or []) if isinstance(x, dict)]
    matched = None
    if lines and want:
        for ln in lines:
            if normalize_sku(str(ln.get("sku") or ln.get("name") or "")) == want:
                matched = ln
                break
    if matched is None and lines and len(lines) == 1:
        matched = lines[0]
    if matched is None:
        return brief
    name = str(matched.get("name") or matched.get("sku") or "")
    try:
        qty = int(float(matched.get("qty") or 1))
    except (TypeError, ValueError):
        qty = 1
    out = dict(brief)
    out["product_name"] = name
    out["quantity"] = max(qty, 1)
    out["lines"] = [matched]
    out["combo"] = False
    out["selected_line_sku"] = normalize_sku(str(matched.get("sku") or name))
    return out


def _resolve_order_quantity(
    case: dict[str, Any],
    *,
    quantity: int | None,
    order_brief: dict[str, Any],
    pay: dict[str, Any],
) -> int:
    """人类改量优先；其次议价回执明确数量；最后才用 brief 初询量。"""
    if quantity is not None:
        try:
            q = int(quantity)
            if q > 0:
                return q
        except (TypeError, ValueError):
            pass
    # 案上显式最终量（议价后写回）
    decided = (case.get("brief") or {}).get("decided_quantity")
    try:
        if decided is not None and int(decided) > 0:
            return int(decided)
    except (TypeError, ValueError):
        pass
    for key in ("negotiate_rounds", "dialog_rounds"):
        rounds = case.get(key) or []
        if not isinstance(rounds, list) or not rounds:
            continue
        last = rounds[-1] if isinstance(rounds[-1], dict) else {}
        res = last.get("result") if isinstance(last.get("result"), dict) else last
        if not isinstance(res, dict):
            continue
        prod = res.get("product") if isinstance(res.get("product"), dict) else {}
        for cand in (res.get("ordered_quantity"), prod.get("quantity"), res.get("quantity")):
            try:
                if cand is not None and int(cand) > 0:
                    return int(cand)
            except (TypeError, ValueError):
                pass
    prod = pay.get("product") if isinstance(pay.get("product"), dict) else {}
    for cand in (prod.get("quantity"), pay.get("quantity"), order_brief.get("quantity")):
        try:
            if cand is not None and int(cand) > 0:
                return int(cand)
        except (TypeError, ValueError):
            pass
    return 1


def _settle_order_price(
    *,
    supplier_agent_id: str | None,
    sku: str | None,
    qty: int,
    list_unit: float,
) -> tuple[float, float, dict[str, Any]]:
    """按供应政策结算挂牌/满量折扣后的单价与货价。"""
    from agents.supplier_common.promo import settle_quote_economics
    from commerce.group_mq import _load_agent_policy

    pol: dict[str, Any] = {}
    try:
        if supplier_agent_id:
            pol = _load_agent_policy(str(supplier_agent_id)) or {}
    except Exception:  # noqa: BLE001
        pol = {}
    econ = settle_quote_economics(
        pol or {},
        qty=qty,
        unit_price=float(list_unit),
        freight=None,
        rfq_payload={},
        sku=str(sku or ""),
    )
    unit = float(econ.get("unit_price") or list_unit)
    goods = float(econ.get("goods_after_promo") or econ.get("goods_total") or round(unit * qty, 2))
    return unit, goods, econ


def step_decide(
    case_id: str,
    action: str,
    *,
    supplier_agent_id: str | None = None,
    goal: str | None = None,
    sku: str | None = None,
    quantity: int | None = None,
) -> dict[str, Any]:
    case = pc.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    if case["state"] not in ("COMPARE_PENDING", "NEGOTIATE_REVIEW", "BID_REVIEW"):
        raise ValueError(f"状态 {case['state']} 不能做三选决策")
    action = action.strip().lower()
    if action == "order":
        try:
            from agents.supplier_common.catalog_price import normalize_sku as _norm_sku
        except Exception:  # noqa: BLE001
            def _norm_sku(text: str | None) -> str | None:  # type: ignore
                return str(text).strip().upper() if text else None

        want_sku = _norm_sku(sku)
        # BID_REVIEW：优先用组群竞价/TCO 方案；否则回退 RFQ 比价
        auction_bids = case.get("auction_bids") or []
        schemes = (case.get("auction_summary") or {}).get("schemes") or []
        if case["state"] == "BID_REVIEW" and (auction_bids or schemes):
            if not supplier_agent_id:
                if schemes:
                    supplier_agent_id = schemes[0].get("supplier_agent_id")
                else:
                    ranked = (case.get("auction_summary") or {}).get("ranked") or [
                        b for b in auction_bids if b.get("unit_price") is not None
                    ]
                    ranked = sorted(
                        ranked,
                        key=lambda b: float(b.get("tco") or b.get("unit_price") or 1e18),
                    )
                    if not ranked:
                        raise ValueError("无竞价结果可选")
                    supplier_agent_id = ranked[0].get("supplier_agent_id")
            scheme = next(
                (s for s in schemes if s.get("supplier_agent_id") == supplier_agent_id),
                None,
            )
            bid = next(
                (b for b in auction_bids if b.get("supplier_agent_id") == supplier_agent_id),
                None,
            )
            if not bid and not scheme:
                raise ValueError("找不到该供应商竞价结果")
            # 竞价也是一物料一案口径：用收窄后的行数量
            narrow0 = _narrow_brief_for_order(case["brief"], sku=want_sku)
            qty = int(narrow0.get("quantity") or case["brief"].get("quantity") or 1)
            unit = float((scheme or bid).get("unit_price"))
            shipping = (scheme or bid).get("shipping_cost")
            quote = {
                "payload": {
                    "supplier_agent_id": supplier_agent_id,
                    "unit_price": unit,
                    "currency": "CNY",
                    "tax_included": True,
                    "shipping_cost": shipping,
                    "quote_id": (bid or {}).get("bid_id") or (scheme or {}).get("bid_id"),
                    "sku": narrow0.get("selected_line_sku") or want_sku,
                    "product_name": narrow0.get("product_name"),
                    "product": {"quantity": qty, "sku": narrow0.get("selected_line_sku") or want_sku},
                    "lead_time_days": (scheme or bid).get("lead_time_days"),
                    "source": "group_auction",
                }
            }
        else:
            if not supplier_agent_id:
                rows = (case.get("comparison") or {}).get("quotes") or []
                if not rows:
                    raise ValueError("无报价可选")
                supplier_agent_id = rows[0].get("supplier_agent_id")
            candidates = [
                q
                for q in case.get("quotes") or []
                if (q.get("payload") or {}).get("supplier_agent_id") == supplier_agent_id
            ]
            quote = None
            if want_sku and candidates:
                for q in candidates:
                    pay = q.get("payload") or {}
                    qsku = _norm_sku(str(pay.get("sku") or pay.get("product_name") or ""))
                    if qsku == want_sku:
                        quote = q
                        break
            if quote is None and candidates:
                quote = candidates[0]
            if not quote:
                raise ValueError("找不到该供应商报价")
        pay = quote.get("payload") or {}
        order_brief = _narrow_brief_for_order(
            case["brief"],
            sku=want_sku or str(pay.get("sku") or ""),
            quote_payload=pay,
        )
        qty = _resolve_order_quantity(
            case, quantity=quantity, order_brief=order_brief, pay=pay
        )
        # 人类改量后写回 brief，避免工单再吃初询 300
        order_brief = dict(order_brief)
        order_brief["quantity"] = qty
        if isinstance(order_brief.get("lines"), list) and order_brief["lines"]:
            line0 = dict(order_brief["lines"][0]) if isinstance(order_brief["lines"][0], dict) else {}
            line0["qty"] = qty
            order_brief["lines"] = [line0]
        try:
            brief_patch = dict(case.get("brief") or {})
            brief_patch["quantity"] = qty
            if isinstance(brief_patch.get("lines"), list) and len(brief_patch["lines"]) == 1:
                ln = dict(brief_patch["lines"][0]) if isinstance(brief_patch["lines"][0], dict) else {}
                ln["qty"] = qty
                brief_patch["lines"] = [ln]
            pc.update_case(case_id, brief=brief_patch)
            case = pc.get_case(case_id) or case
        except Exception:  # noqa: BLE001
            pass

        # 确保报价 payload 带本行数量，供 build_order_draft 优先使用
        pay2 = dict(pay)
        pay2.setdefault("sku", order_brief.get("selected_line_sku") or pay.get("sku"))
        pay2.setdefault("product_name", order_brief.get("product_name") or pay.get("product_name"))
        prod = dict(pay2.get("product") or {}) if isinstance(pay2.get("product"), dict) else {}
        prod["quantity"] = qty
        if order_brief.get("selected_line_sku"):
            prod["sku"] = order_brief["selected_line_sku"]
        list_unit = float(pay2.get("unit_price") or prod.get("unit_price") or 0)
        unit_settled, goods_settled, econ = _settle_order_price(
            supplier_agent_id=supplier_agent_id,
            sku=str(prod.get("sku") or pay2.get("sku") or want_sku or ""),
            qty=qty,
            list_unit=list_unit,
        )
        pay2["unit_price"] = unit_settled
        pay2["goods_total"] = goods_settled
        pay2["goods_after_promo"] = goods_settled
        pay2["promo_settlement"] = econ
        if econ.get("policy_hints"):
            pay2["policy_hints"] = econ.get("policy_hints")
        pay2["product"] = prod
        pay2["quantity"] = qty
        quote = {**quote, "payload": pay2}
        draft_env = build_order_draft(
            business_id=case_id,
            purchase_request=order_brief,
            selected_quote=quote,
        )
        from_group = (quote.get("payload") or {}).get("source") == "group_auction"
        ship_already = (quote.get("payload") or {}).get("shipping_cost") is not None
        if from_group and ship_already:
            hitl_order = make_hitl(
                "confirm_order",
                "组群TCO方案已含运费；请到「工单待办」双边确认后生成电子订单/发票",
            )
        else:
            hitl_order = make_hitl(
                "request_shipping",
                "运费未定时：可自己联系物流，或请对方联系物流后再生成合同；勿把运费当 0；并请到「工单待办」确认订单",
            )
        updated = pc.transition(
            case_id,
            "ORDER_DRAFT",
            event="decide_order",
            patch={
                "decision": {"action": "order", "supplier_agent_id": supplier_agent_id},
                "selected_supplier": supplier_agent_id,
                "order_draft": draft_env,
                "hitl_pending": hitl_order,
            },
        )
        # 订单草案就绪 → 双边工单 + 通知（用户自行点确认，双方确认后才发电子订单/发票）
        try:
            from commerce.order_tickets import spawn_order_ticket_from_case

            ticket_meta = spawn_order_ticket_from_case(updated, buyer_agent_id=_buyer_agent_id())
            return pc.update_case(
                case_id,
                order_ticket_id=ticket_meta.get("ticket_id"),
                order_ticket=ticket_meta,
            )
        except Exception as exc:  # noqa: BLE001
            report(f"订单工单创建失败：{exc}", phase="warn")
            return updated
    if action == "negotiate":
        # 议价目标用人话口径；禁止把预算数字塞进出站目标（预算非必填）
        nego_goal = goal or "保质保交期前提下优化总价；请谈活动满减/补贴条件，不要死压单价"
        return pc.transition(
            case_id,
            "NEGOTIATING",
            event="decide_negotiate",
            patch={
                "decision": {"action": "negotiate", "goal": nego_goal},
                "negotiate_goal": nego_goal,
                "hitl_pending": None,
            },
        )
    if action == "auction":
        return pc.transition(
            case_id,
            "BIDDING",
            event="decide_auction",
            patch={"decision": {"action": "auction"}, "hitl_pending": None},
        )
    raise ValueError("action 须为 order|negotiate|auction")


async def step_negotiate(case_id: str) -> dict[str, Any]:
    case = pc.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    if case["state"] != "NEGOTIATING":
        raise ValueError("不在议价状态")
    goal = case.get("negotiate_goal") or "优化总价"
    rounds: list[dict[str, Any]] = []
    report(f"开始 AIP 议价轮 · 目标：{goal}", phase="aip")
    for partner in case["shortlist"]:
        meta = _supplier_meta(partner["agent_id"])
        label = partner.get("name") or partner["agent_id"]
        report(f"经 AIP 与「{label}」议价中…", phase="aip")
        # 取该供应商上一轮报价
        prev = next(
            (q for q in case.get("quotes") or [] if (q.get("payload") or {}).get("supplier_agent_id") == partner["agent_id"]),
            None,
        )
        prev_price = (prev or {}).get("payload", {}).get("unit_price")
        dest = (case.get("brief") or {}).get("destination") or {
            "province": "河北",
            "city": "保定",
            "postal_code": "071000",
        }
        if not isinstance(dest, dict):
            dest = {"province": "河北", "city": "保定", "postal_code": "071000"}
        dest.setdefault("province", "河北")
        envelope = wrap_business(
            "agentlink.bargain_round",
            case_id,
            {
                "round": len(case.get("negotiate_rounds") or []) + 1,
                "goal_text": goal,  # 不传预算数字
                "previous_quote_id": (prev or {}).get("payload", {}).get("quote_id"),
                "previous_unit_price": prev_price,
                "product_name": case["brief"]["product_name"],
                "quantity": case["brief"]["quantity"],
                "specifications": case["brief"].get("specifications") or {},
                "need_freight": False,
                "destination": dest,
                "postal_code": dest.get("postal_code") or "071000",
                "dest_province": dest.get("province") or "河北",
            },
        )
        try:
            out = await aip_start_structured(
                partner_url=meta["url"] or partner.get("endpoint"),
                leader_aic=LEADER_AIC(),
                partner_aic=meta["aic"],
                session_id=f"flow-neg-{case_id}-{partner['agent_id']}",
                envelope=envelope,
                local_agent_id="buyer-a",
            )
            rounds.append({"supplier": partner["agent_id"], "result": out.get("envelope"), "state": out.get("state")})
            report(f"「{label}」议价回执 · {out.get('state')}", phase="aip")
            if out.get("envelope"):
                # 用议价结果替换 quotes 中对应项
                new_quotes = [
                    q
                    for q in case.get("quotes") or []
                    if (q.get("payload") or {}).get("supplier_agent_id") != partner["agent_id"]
                ]
                env = out["envelope"]
                env.setdefault("payload", {})["supplier_agent_id"] = partner["agent_id"]
                new_quotes.append(env)
                case = pc.update_case(case_id, quotes=new_quotes)
        except Exception as exc:  # noqa: BLE001
            rounds.append({"supplier": partner["agent_id"], "error": str(exc)})

    case = pc.get_case(case_id) or case
    comparison = compare_quotes(case.get("quotes") or [])
    dest_province = "河北"
    try:
        dest = (case.get("brief") or {}).get("destination") or {}
        if isinstance(dest, dict) and dest.get("province"):
            dest_province = str(dest["province"])
    except Exception:  # noqa: BLE001
        pass
    # 预算非必填：仅当 case 上自愿留下 soft 提示时才用于排序
    soft_budget = None
    budget_posture = None
    brief = case.get("brief") or {}
    if brief.get("budget_posture") in ("ample", "tight"):
        budget_posture = brief.get("budget_posture")
    if brief.get("soft_budget") is not None:
        try:
            soft_budget = float(brief["soft_budget"])
        except (TypeError, ValueError):
            soft_budget = None
    scheme_pack = plan_procurement_schemes(
        quotes=case.get("quotes") or [],
        base_qty=int((case.get("brief") or {}).get("quantity") or 1),
        dest_province=dest_province,
        soft_budget=soft_budget,
        budget_posture=budget_posture,
    )
    hist = list(case.get("negotiate_rounds") or [])
    hist.append({"at": datetime.now(timezone.utc).isoformat(), "goal": goal, "rounds": rounds})
    n_schemes = len(scheme_pack.get("schemes") or [])
    report(
        f"议价汇总 · 生成方案 {n_schemes} 条（满减/补贴/拆单；预算非必填）",
        phase="aip",
    )
    return pc.transition(
        case_id,
        "NEGOTIATE_REVIEW",
        event="negotiate_done",
        patch={
            "negotiate_rounds": hist,
            "comparison": comparison,
            "procurement_schemes": scheme_pack,
            "hitl_pending": make_hitl(
                "negotiate_review",
                f"议价结果已回，已准备 {n_schemes} 条方案（现量 / 凑满减或补贴 / 拆单）；"
                "无需交代预算也可选；预算紧看拆单，宽裕可看活动门槛",
                options=["negotiate", "auction", "order"],
            ),
        },
    )


async def step_auction(case_id: str) -> dict[str, Any]:
    """匿名竞价：默认走 ACPs Group 广播；失败则回退 N 次 1:1 AIP RPC。"""
    case = pc.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    if case["state"] != "BIDDING":
        raise ValueError("不在竞价状态")

    brief = case.get("brief") or {}
    lines = [x for x in (brief.get("lines") or []) if isinstance(x, dict)]
    line0 = lines[0] if lines else {}
    auc_sku = str(brief.get("selected_line_sku") or line0.get("sku") or "")
    auc_name = str(line0.get("name") or brief.get("product_name") or "")
    auc_qty = int(float(line0.get("qty") or brief.get("quantity") or 1))
    specs = dict(brief.get("specifications") or {})
    if auc_sku:
        specs.setdefault("sku", auc_sku)
    envelope = wrap_business(
        "agentlink.blind_bid",
        case_id,
        {
            "auction_id": f"auc-{case_id}",
            "product_name": auc_name or brief.get("product_name"),
            "sku": auc_sku or None,
            "quantity": auc_qty,
            "specifications": specs,
            "sealed": True,
        },
    )
    bids: list[dict[str, Any]] = []
    auction_meta: dict[str, Any] = {"transport": "rpc"}
    timings: dict[str, Any] = {}
    t_auction0 = time.perf_counter()
    use_group = (os.getenv("ACPS_GROUP_AUCTION") or "1").strip() not in (
        "0",
        "false",
        "False",
        "no",
    )

    def _priced(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [b for b in rows if b.get("unit_price") is not None]

    if use_group:
        try:
            from commerce import group_mq as gm

            member_ids = [p["agent_id"] for p in case["shortlist"] if p.get("agent_id")]
            # 仅邀请短名单供应商入组盲拍。物流旁听并行 invite 会拖垮 Leader AMQP
            # consumer（实证：A/C 可 joined；A/C+logistics 常全 Timeout / Consumer cancelled）。
            # TCO：供应出价成功后再尝试把 logistics 拉入（失败则仅货价排序）。
            dest = buyer_destination(_buyer_agent_id())
            report("组群竞价：建组盲拍（供应入组）…", phase="group")
            t_g0 = time.perf_counter()
            gout = await gm.run_group_blind_auction(
                leader_aic=LEADER_AIC(),
                leader_agent_id="buyer-a",
                member_agent_ids=member_ids,
                bid_envelope=envelope,
                with_tco=False,
                dest_postal=str(dest.get("postal_code") or "071000"),
                quantity=auc_qty,
            )
            # 若供应已出价，再开一场带物流的 TCO 合入（可选；失败保留纯货价榜）
            if _priced(gout.get("bids") or []) and "logistics" not in member_ids:
                try:
                    report("组群竞价：二次建组合入物流 TCO…", phase="group")
                    gout2 = await gm.run_group_blind_auction(
                        leader_aic=LEADER_AIC(),
                        leader_agent_id="buyer-a",
                        member_agent_ids=[*member_ids, "logistics"],
                        bid_envelope=envelope,
                        with_tco=True,
                        dest_postal=str(dest.get("postal_code") or "071000"),
                        quantity=auc_qty,
                    )
                    if _priced(gout2.get("bids") or []) or (gout2.get("schemes") or []):
                        gout = gout2
                except Exception as _tco_exc:  # noqa: BLE001
                    report(f"物流 TCO 合入失败，沿用货价榜：{_tco_exc}", phase="group")
            timings["group_ms"] = round((time.perf_counter() - t_g0) * 1000.0, 1)
            timings["group_invite_ms"] = gout.get("invite_elapsed_ms")
            timings["group_early_abort"] = bool(gout.get("early_abort"))
            if gout.get("abort_reason"):
                timings["group_abort_reason"] = gout.get("abort_reason")
            bids = gout.get("bids") or []
            schemes = gout.get("schemes") or []
            auction_meta = {
                "transport": "group",
                "session_id": gout.get("session_id"),
                "group_id": gout.get("group_id"),
                "task_id": gout.get("task_id"),
                "offers_got": gout.get("offers_got"),
                "schemes": schemes,
                "tco_enabled": True,
                "early_abort": bool(gout.get("early_abort")),
                "abort_reason": gout.get("abort_reason"),
            }
            report(
                f"组群竞价回执 · {len(_priced(bids))} 家出价"
                f" · TCO方案 {len(schemes)}"
                + (" · 早停回退" if gout.get("early_abort") else ""),
                phase="group",
            )
            # 组已建但无人有效出价（邀请超时/旁听全 skip）→ 必须回退 RPC，否则 BID_REVIEW 空榜
            if not _priced(bids) and not schemes:
                report("组群无有效出价，回退并行 AIP 盲拍…", phase="group")
                bids = []
                auction_meta = {
                    "transport": "rpc",
                    "group_empty_fallback": True,
                    "early_abort": bool(gout.get("early_abort")),
                    "abort_reason": gout.get("abort_reason"),
                }
        except Exception as exc:  # noqa: BLE001
            report(f"组群竞价失败，回退 RPC：{exc}", phase="group")
            bids = []
            auction_meta = {"transport": "rpc"}
            timings["group_error"] = str(exc)[:200]

    if not _priced(bids):
        auction_meta = (
            {**auction_meta, "transport": "rpc"}
            if auction_meta.get("group_empty_fallback")
            else {"transport": "rpc", **{k: auction_meta[k] for k in ("early_abort", "abort_reason") if k in auction_meta}}
        )
        partners = [
            p
            for p in case["shortlist"]
            if str(p.get("agent_id") or "") not in ("", "logistics")
        ]

        async def _rpc_one(partner: dict[str, Any]) -> dict[str, Any]:
            meta = _supplier_meta(partner["agent_id"])
            try:
                out = await aip_start_structured(
                    partner_url=meta["url"] or partner.get("endpoint"),
                    leader_aic=LEADER_AIC(),
                    partner_aic=meta["aic"],
                    session_id=f"flow-bid-{case_id}-{partner['agent_id']}",
                    envelope=envelope,
                    local_agent_id="buyer-a",
                )
                payload = (out.get("envelope") or {}).get("payload") or {}
                return {
                    "supplier_agent_id": partner["agent_id"],
                    "unit_price": payload.get("unit_price"),
                    "lead_time_days": payload.get("lead_time_days"),
                    "bid_id": payload.get("bid_id"),
                    "transport": "rpc",
                    "raw": out.get("envelope"),
                }
            except Exception as exc:  # noqa: BLE001
                return {"supplier_agent_id": partner["agent_id"], "error": str(exc)}

        report(f"并行 RPC 盲拍 · {len(partners)} 家…", phase="aip")
        t_r0 = time.perf_counter()
        rpc_bids = list(await asyncio.gather(*[_rpc_one(p) for p in partners]))
        timings["rpc_parallel_ms"] = round((time.perf_counter() - t_r0) * 1000.0, 1)
        timings["rpc_parallel_n"] = len(partners)
        bids = rpc_bids
        auction_meta["rpc_parallel"] = True

    schemes = list(auction_meta.get("schemes") or [])
    if schemes:
        bids_sorted = sorted(
            [b for b in bids if b.get("unit_price") is not None],
            key=lambda b: (
                b.get("tco") is None,
                float(b["tco"]) if b.get("tco") is not None else float(b["unit_price"]),
            ),
        )
        hitl_msg = (
            "组群竞价+物流TCO方案（仅采购可见）；请按方案选商下单"
            + (
                f"；最优TCO={schemes[0].get('tco')}（{schemes[0].get('supplier_agent_id')}）"
                if schemes[0].get("tco") is not None
                else ""
            )
        )
    else:
        bids_sorted = sorted(
            [b for b in bids if b.get("unit_price") is not None],
            key=lambda b: float(b["unit_price"]),
        )
        hitl_msg = "组群/匿名竞价汇总（仅采购可见）；请选定供应商生成草案"
    timings["auction_total_ms"] = round((time.perf_counter() - t_auction0) * 1000.0, 1)
    timings["priced"] = len(_priced(bids))
    summary = {
        **auction_meta,
        "ranked": bids_sorted,
        "schemes": schemes or list(auction_meta.get("schemes") or []),
        "timings_ms": timings,
    }
    from commerce.choice_actions import post_auction_scheme_choices

    pending = post_auction_scheme_choices(
        case_id=case_id,
        schemes=summary.get("schemes") or [],
        bids=bids,
    )
    report(
        f"竞价完成 · transport={summary.get('transport')} · priced={timings['priced']}"
        f" · total={timings['auction_total_ms']}ms",
        phase="group" if summary.get("transport") == "group" else "aip",
    )
    patch: dict[str, Any] = {
        "auction_bids": bids,
        "auction_summary": summary,
        "hitl_pending": make_hitl(
            "bid_review",
            hitl_msg,
            options=["order"],
        ),
    }
    if pending:
        patch["pending_choices"] = pending
    return pc.transition(
        case_id,
        "BID_REVIEW",
        event="auction_done",
        patch=patch,
    )


def _shipping_mass_from_case(case: dict[str, Any], *, fallback_kg: float = 200.0) -> dict[str, Any]:
    """从订单草案/报价全量规格推导询运重量与体积；有规格绝不瞎用默认吨位。"""
    from commerce.seat_catalog import estimate_weight_kg, product_physical_specs
    from agents.supplier_common.catalog_price import normalize_sku

    draft = (case.get("order_draft") or {}).get("payload") or {}
    qty = float(draft.get("quantity") or (case.get("brief") or {}).get("quantity") or 1)
    sku = normalize_sku(str(draft.get("sku") or draft.get("product_name") or ""))
    weight = draft.get("weight_kg")
    volume = draft.get("volume_m3")
    charge_class = draft.get("charge_class")
    if weight is None or volume is None:
        phys = product_physical_specs(sku, qty=qty) if sku else {}
        if weight is None:
            weight = phys.get("weight_kg") or estimate_weight_kg(sku, qty)
        if volume is None:
            volume = phys.get("volume_m3")
        charge_class = charge_class or phys.get("charge_class")
    # 再从 quotes 里捞同 SKU 回执规格
    if weight is None:
        for q in case.get("quotes") or []:
            pay = q.get("payload") or {}
            qsku = normalize_sku(str(pay.get("sku") or (pay.get("product") or {}).get("sku") or ""))
            if sku and qsku and qsku != sku:
                continue
            cand = pay.get("weight_kg") or (pay.get("product") or {}).get("weight_kg")
            if cand is not None:
                weight = cand
                volume = volume or pay.get("volume_m3") or (pay.get("product") or {}).get("volume_m3")
                break
    try:
        w = float(weight) if weight is not None else float(fallback_kg)
    except (TypeError, ValueError):
        w = float(fallback_kg)
    try:
        v = float(volume) if volume is not None else None
    except (TypeError, ValueError):
        v = None
    return {
        "weight_kg": max(0.01, round(w, 3)),
        "volume_m3": v,
        "sku": sku,
        "quantity": qty,
        "product_name": draft.get("product_name"),
        "charge_class": charge_class,
        "derived": weight is not None,
    }


async def step_shipping(case_id: str, *, weight_kg: float = 200.0, postal_code: str = "310000") -> dict[str, Any]:
    case = pc.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    if case["state"] not in ("ORDER_DRAFT", "CONTRACT_PENDING"):
        raise ValueError("请先生成订单草案")
    url = os.getenv("LOGISTICS_RPC_URL", "https://127.0.0.1:8015/rpc")
    aic = os.getenv("LOGISTICS_AIC", "logistics-local-aic")
    mass = _shipping_mass_from_case(case, fallback_kg=weight_kg)
    # 调用方显式传入且与默认不同时尊重；否则优先用规格推导
    use_weight = float(mass["weight_kg"])
    if weight_kg not in (None, 200.0, 200) and float(weight_kg) > 0:
        # 仅当调用方明显手填（非默认 200）才覆盖
        if abs(float(weight_kg) - 200.0) > 1e-6:
            use_weight = float(weight_kg)
    report(
        f"经 AIP 向物流询运… sku={mass.get('sku')} qty={mass.get('quantity')} "
        f"weight={use_weight}kg volume={mass.get('volume_m3')}",
        phase="aip",
    )
    dest = {"postal_code": postal_code}
    try:
        from commerce.merchant import buyer_destination

        more = buyer_destination(_buyer_agent_id()) or {}
        if more.get("city"):
            dest["city"] = more["city"]
        if more.get("address"):
            dest["address"] = more["address"]
    except Exception:  # noqa: BLE001
        pass
    envelope = wrap_business(
        "agentlink.shipping_request",
        case_id,
        {
            "weight_kg": use_weight,
            "volume_m3": mass.get("volume_m3"),
            "sku": mass.get("sku"),
            "product_name": mass.get("product_name"),
            "quantity": mass.get("quantity"),
            "charge_class": mass.get("charge_class"),
            "zone": "domestic",
            "destination": dest,
            "postal_code": postal_code,
        },
    )
    out = await aip_start_structured(
        partner_url=url,
        leader_aic=LEADER_AIC(),
        partner_aic=aic,
        session_id=f"flow-ship-{case_id}",
        envelope=envelope,
        local_agent_id="buyer-a",
    )
    ship = out.get("envelope")
    report(f"物流回执 · {out.get('state')}", phase="aip")
    # 合入合同
    draft = (case.get("order_draft") or {}).get("payload") or {}
    ship_pay = (ship or {}).get("payload") or {}
    contract = {
        "contract_id": f"ct-{case_id}",
        "case_id": case_id,
        "supplier_agent_id": case.get("selected_supplier"),
        "goods": draft,
        "shipping": ship_pay,
        "total_estimate": round(
            float(draft.get("goods_total") or 0) + float(ship_pay.get("shipping_cost") or 0),
            2,
        ),
        "status": "CONTRACT_PENDING",
        "buyer_ack": False,
        "supplier_ack": False,
    }
    return pc.transition(
        case_id,
        "CONTRACT_PENDING",
        event="shipping_merged",
        patch={
            "shipping_quote": ship,
            "contract": wrap_business("agentlink.order_contract", case_id, contract),
            "hitl_pending": make_hitl(
                "bilateral_confirm",
                "请采购方确认合同；确认后请求供应商方确认，再激活",
            ),
        },
    )


def step_buyer_confirm(case_id: str) -> dict[str, Any]:
    case = pc.get_case(case_id)
    if not case or case["state"] != "CONTRACT_PENDING":
        raise ValueError("合同未就绪")
    contract = case.get("contract") or {}
    payload = contract.get("payload") or contract
    payload["buyer_ack"] = True
    return pc.update_case(
        case_id,
        buyer_confirmed=True,
        contract=wrap_business("agentlink.order_contract", case_id, payload),
        hitl_pending=make_hitl("supplier_confirm", "已采购确认；请请求供应商确认"),
        audit=(case.get("audit") or [])
        + [{"at": datetime.now(timezone.utc).isoformat(), "event": "buyer_confirmed", "state": "CONTRACT_PENDING"}],
    )


async def step_supplier_confirm(case_id: str) -> dict[str, Any]:
    case = pc.get_case(case_id)
    if not case or not case.get("buyer_confirmed"):
        raise ValueError("须先采购方确认")
    sid = case.get("selected_supplier")
    if not sid:
        raise ValueError("未选定供应商")
    meta = _supplier_meta(sid)
    partner = next((p for p in case.get("shortlist") or [] if p["agent_id"] == sid), {})
    envelope = wrap_business(
        "agentlink.contract_ack",
        case_id,
        {
            "contract_id": (case.get("contract") or {}).get("payload", {}).get("contract_id"),
            "action": "confirm",
            "party": "supplier",
        },
    )
    out = await aip_start_structured(
        partner_url=meta["url"] or partner.get("endpoint"),
        leader_aic=LEADER_AIC(),
        partner_aic=meta["aic"],
        session_id=f"flow-ack-{case_id}",
        envelope=envelope,
        local_agent_id="buyer-a",
    )
    ok = bool(out.get("envelope")) or out.get("state") in ("awaiting-completion", "completed", "accepted")
    contract = case.get("contract") or {}
    payload = dict(contract.get("payload") or {})
    payload["supplier_ack"] = ok
    payload["supplier_ack_result"] = out.get("envelope") or {"state": out.get("state"), "message": out.get("message")}
    return pc.update_case(
        case_id,
        supplier_confirmed=ok,
        contract=wrap_business("agentlink.order_contract", case_id, payload),
        hitl_pending=(
            make_hitl("activate", "双边已确认，可激活订单")
            if ok
            else make_hitl("supplier_confirm", "供应商确认失败，可重试")
        ),
    )


def step_activate(case_id: str) -> dict[str, Any]:
    case = pc.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    if not (case.get("buyer_confirmed") and case.get("supplier_confirmed")):
        raise PermissionError("ACTIVATE_REQUIRES_BILATERAL_HITL")
    return pc.transition(
        case_id,
        "ACTIVE",
        event="activated",
        patch={"hitl_pending": None, "activated_at": datetime.now(timezone.utc).isoformat()},
    )
