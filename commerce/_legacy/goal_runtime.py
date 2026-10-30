"""目标驱动运行时（参考 Claude Code：工具回执结构化缺口 → 下一轮重规划，而非穷举提示词）。

核心契约：
- 每个关键工具回执可带 blockers[] / next_actions[] / system_reminder
- blocker 指明缺什么、谁持有（holder）、用哪个工具补
- 模型只需坚持目标；缺口由工具暴露，禁止脑补数字
"""
from __future__ import annotations

from typing import Any


def blocker(
    *,
    code: str,
    message: str,
    holder: str,
    fields: list[str] | None = None,
    repair_tool: str | None = None,
    repair_hint: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "holder": holder,
        "fields": fields or [],
        "repair_tool": repair_tool,
        "repair_hint": repair_hint,
    }


def with_runtime_meta(
    payload: dict[str, Any],
    *,
    goal: str | None = None,
    blockers: list[dict[str, Any]] | None = None,
    next_actions: list[str] | None = None,
) -> dict[str, Any]:
    """给工具回执打上 Claude Code 风格的续跑元数据。"""
    out = dict(payload)
    bl = list(blockers or [])
    out["ok"] = bool(payload.get("ok", not bl and not payload.get("error")))
    if goal:
        out["goal"] = goal
    out["blockers"] = bl
    if next_actions is None and bl:
        next_actions = []
        for b in bl:
            t = b.get("repair_tool")
            if t and t not in next_actions:
                next_actions.append(str(t))
        if "flow.inspect_goal" not in next_actions:
            next_actions.insert(0, "flow.inspect_goal")
    if next_actions is not None:
        out["next_actions"] = next_actions
    if bl:
        lines = [f"- [{b.get('code')}] {b.get('message')}（持有方={b.get('holder')}）" for b in bl]
        out["system_reminder"] = (
            "<system-reminder>\n"
            "当前目标被下列缺口挡住。先诊断再换战术：调用 repair_tool 向持有方补数，"
            "禁止编造体积/重量/价格；补齐后重试原目标工具。\n"
            + "\n".join(lines)
            + "\n</system-reminder>"
        )
    return out


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def collect_physical_specs(*sources: dict[str, Any] | None) -> dict[str, Any]:
    """从多源合并体积/重量等物理规格。"""
    out: dict[str, Any] = {}
    for src in sources:
        if not isinstance(src, dict):
            continue
        prod = src.get("product") if isinstance(src.get("product"), dict) else {}
        phys = src.get("physical_specs") if isinstance(src.get("physical_specs"), dict) else {}
        for key in ("volume_m3", "weight_kg", "kg_per_unit", "pack_cm", "charge_class", "sku", "quantity"):
            if out.get(key) is None:
                cand = src.get(key)
                if cand is None:
                    cand = prod.get(key)
                if cand is None:
                    cand = phys.get(key)
                if cand is not None:
                    out[key] = cand
    return out


def shipping_blockers_from_mass(mass: dict[str, Any] | None, *, order_ticket_id: str | None = None) -> list[dict[str, Any]]:
    mass = mass or {}
    bl: list[dict[str, Any]] = []
    if _num(mass.get("volume_m3")) is None:
        bl.append(
            blocker(
                code="MISSING_VOLUME",
                message="下承运单需要总体积 volume_m3，当前订单/报价未齐",
                holder="supplier",
                fields=["volume_m3"],
                repair_tool="flow.backfill_specs",
                repair_hint="向供应或物料主数据补体积后写回订单，再 flow.request_shipping / place_logistics_order",
            )
        )
    if _num(mass.get("weight_kg")) is None:
        bl.append(
            blocker(
                code="MISSING_WEIGHT",
                message="下承运单需要重量 weight_kg，当前订单/报价未齐",
                holder="supplier",
                fields=["weight_kg"],
                repair_tool="flow.backfill_specs",
                repair_hint="向供应或物料主数据补重量后写回订单",
            )
        )
    if order_ticket_id:
        for b in bl:
            b["order_ticket_id"] = order_ticket_id
    return bl


def inspect_case_goal(
    case: dict[str, Any] | None,
    *,
    agent_id: str,
    order_ticket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """诊断本案相对「货物成交 → 承运生效」的缺口。"""
    case = case or {}
    state = str(case.get("state") or "DRAFT")
    brief = case.get("brief") or {}
    draft = (case.get("order_draft") or {}).get("payload") if isinstance(case.get("order_draft"), dict) else {}
    draft = draft if isinstance(draft, dict) else {}

    goal = "承运订单双方确认生效" if state in ("ORDER_DRAFT", "CONTRACT_PENDING", "ACTIVE") else "货物订单双方确认生效"
    blockers: list[dict[str, Any]] = []
    next_actions: list[str] = []

    if state in ("DRAFT", "DISCOVERING", "SHORTLIST_PENDING"):
        if not brief.get("product_name") and not brief.get("lines"):
            blockers.append(
                blocker(
                    code="NO_DEMAND",
                    message="尚未绑定采购需求",
                    holder="buyer_human",
                    repair_tool="discover.suppliers",
                )
            )
        else:
            next_actions = ["discover.suppliers", "rfq.send_batch"]
    elif state in ("SOURCING", "COMPARE_PENDING", "NEGOTIATING", "NEGOTIATE_REVIEW"):
        next_actions = ["partner.dialog", "flow.decide_order"]
        if not (case.get("quotes") or case.get("rfq_batch")):
            blockers.append(
                blocker(
                    code="NO_QUOTES",
                    message="尚无有效询价回执",
                    holder="supplier",
                    repair_tool="rfq.send_batch",
                )
            )
    elif state in ("ORDER_DRAFT", "CONTRACT_PENDING"):
        next_actions = ["flow.request_shipping", "flow.place_logistics_order"]
        mass = collect_physical_specs(draft)
        if order_ticket:
            st = order_ticket.get("state") or {}
            summary = st.get("summary") if isinstance(st.get("summary"), dict) else {}
            mass = collect_physical_specs(summary, draft, mass)
        # 尝试主数据兜底诊断（有 SKU 则可 backfill，不算永久缺口）
        sku = mass.get("sku") or draft.get("sku")
        if (_num(mass.get("volume_m3")) is None or _num(mass.get("weight_kg")) is None) and sku:
            try:
                from commerce.seat_catalog import product_physical_specs

                phys = product_physical_specs(str(sku), qty=float(mass.get("quantity") or draft.get("quantity") or 1))
                mass = collect_physical_specs(mass, phys)
            except Exception:  # noqa: BLE001
                pass
        blockers.extend(
            shipping_blockers_from_mass(
                mass,
                order_ticket_id=str((order_ticket or {}).get("id") or "") or None,
            )
        )
        if not (order_ticket and (order_ticket.get("state") or {}).get("order_effective")):
            if state == "ORDER_DRAFT":
                blockers.append(
                    blocker(
                        code="ORDER_NOT_EFFECTIVE",
                        message="货物工单尚未双方确认生效",
                        holder="buyer_human",
                        repair_tool="ui.offer_choices",
                        repair_hint="请人类在工单待办确认订单",
                    )
                )
    elif state == "ACTIVE":
        goal = "已完成（可归档）"
        next_actions = []

    # 人类改量未落地
    decided = brief.get("decided_quantity")
    try:
        if decided is not None and draft.get("quantity") is not None and int(decided) != int(draft.get("quantity")):
            blockers.append(
                blocker(
                    code="QTY_MISMATCH",
                    message=f"人类决定量 {decided} 与订单草案量 {draft.get('quantity')} 不一致",
                    holder="buyer",
                    fields=["quantity"],
                    repair_tool="flow.decide_order",
                    repair_hint=f"重新 flow.decide_order(quantity={decided})",
                )
            )
    except (TypeError, ValueError):
        pass

    return with_runtime_meta(
        {
            "case_id": case.get("case_id"),
            "state": state,
            "product_name": brief.get("product_name") or draft.get("product_name"),
            "quantity": draft.get("quantity") or brief.get("decided_quantity") or brief.get("quantity"),
            "selected_supplier": case.get("selected_supplier"),
            "mass": collect_physical_specs(
                draft,
                ((order_ticket.get("state") or {}).get("summary") if isinstance(order_ticket, dict) else None),
            ),
        },
        goal=goal,
        blockers=blockers,
        next_actions=next_actions or (["flow.inspect_goal"] if blockers else []),
    )


def patch_order_specs(
    agent_id: str,
    *,
    order_ticket_id: str | None,
    case_id: str | None,
    specs: dict[str, Any],
) -> dict[str, Any]:
    """把补到的规格写回订单工单 summary 与案 order_draft。"""
    from commerce import procurement_case as pc
    from commerce import tickets as tk

    written: dict[str, Any] = {"ticket": False, "case": False}
    clean = {k: v for k, v in (specs or {}).items() if v is not None}

    if order_ticket_id:
        t = tk.get_ticket(agent_id, order_ticket_id)
        if t:
            st = dict(t.get("state") or {})
            summary = dict(st.get("summary") or {})
            summary.update({k: clean[k] for k in ("volume_m3", "weight_kg", "pack_cm", "kg_per_unit", "charge_class") if k in clean})
            if clean.get("sku"):
                summary["sku"] = clean["sku"]
            prod = dict(summary.get("product") or {}) if isinstance(summary.get("product"), dict) else {}
            prod.update({k: clean[k] for k in ("volume_m3", "weight_kg", "pack_cm") if k in clean})
            summary["product"] = prod
            st["summary"] = summary
            st["specs_backfilled_at"] = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()
            tk.save_state(agent_id, order_ticket_id, st, actor=agent_id)
            written["ticket"] = True
            if not case_id:
                case_id = str(t.get("case_id") or summary.get("case_id") or "") or None

    if case_id:
        case = pc.get_case(case_id)
        if case:
            draft_env = dict(case.get("order_draft") or {})
            pay = dict(draft_env.get("payload") or draft_env)
            pay.update({k: clean[k] for k in ("volume_m3", "weight_kg", "pack_cm", "kg_per_unit", "charge_class") if k in clean})
            if clean.get("sku"):
                pay["sku"] = clean["sku"]
            phys = dict(pay.get("physical_specs") or {})
            phys.update(clean)
            pay["physical_specs"] = phys
            draft_env["payload"] = pay
            if "schema_type" not in draft_env:
                # 兼容纯 payload 存法
                pc.update_case(case_id, order_draft={"payload": pay})
            else:
                pc.update_case(case_id, order_draft=draft_env)
            written["case"] = True

    return {"ok": True, "written": written, "specs": clean, "case_id": case_id, "order_ticket_id": order_ticket_id}


async def backfill_specs(
    agent_id: str,
    *,
    case_id: str | None = None,
    order_ticket_id: str | None = None,
    supplier_agent_id: str | None = None,
    ask_supplier: bool = True,
) -> dict[str, Any]:
    """补齐物理规格：先主数据，再必要时问供应；写回后再返回可续跑状态。"""
    from commerce import procurement_case as pc
    from commerce import tickets as tk
    from commerce.seat_catalog import product_physical_specs
    from agents.supplier_common.catalog_price import normalize_sku

    order = tk.get_ticket(agent_id, order_ticket_id) if order_ticket_id else None
    case = pc.get_case(case_id) if case_id else None
    if not case and order:
        case = pc.get_case(str(order.get("case_id") or ""))
        case_id = str((case or {}).get("case_id") or "") or case_id

    draft = ((case or {}).get("order_draft") or {}).get("payload") if case else {}
    draft = draft if isinstance(draft, dict) else {}
    summary = ((order or {}).get("state") or {}).get("summary") if order else {}
    summary = summary if isinstance(summary, dict) else {}

    sku = normalize_sku(str(draft.get("sku") or summary.get("sku") or draft.get("product_name") or ""))
    qty = float(draft.get("quantity") or summary.get("quantity") or 1)
    sources: list[dict[str, Any]] = [draft, summary]
    supplier_reply: dict[str, Any] | None = None

    # 1) 本地主数据
    if sku:
        try:
            sources.append(product_physical_specs(sku, qty=qty) or {})
        except Exception:  # noqa: BLE001
            pass

    mass = collect_physical_specs(*sources)
    # 2) 仍缺则问供应
    if ask_supplier and (_num(mass.get("volume_m3")) is None or _num(mass.get("weight_kg")) is None):
        sid = supplier_agent_id or (case or {}).get("selected_supplier") or summary.get("supplier_agent_id")
        if sid and case_id:
            try:
                from commerce.buyer_tools.service import get_buyer_tools

                tools = get_buyer_tools()
                tools.set_active_case(case_id)
                dlg = await tools.partner_dialog(
                    {
                        "case_id": case_id,
                        "partner": sid,
                        "intent": "clarify",
                        "goal_text": (
                            f"请补充 SKU={sku or draft.get('product_name')} 数量{qty} 的包装规格："
                            "volume_m3、weight_kg、pack_cm、kg_per_unit；只要参数不要改价。"
                        ),
                        "message": "物流下单缺物理规格，请返回体积与重量",
                    }
                )
                supplier_reply = dlg
                res = (dlg or {}).get("result") if isinstance(dlg, dict) else {}
                if isinstance(res, dict):
                    sources.append(res)
                    if isinstance(res.get("product"), dict):
                        sources.append(res["product"])
                mass = collect_physical_specs(*sources)
            except Exception as exc:  # noqa: BLE001
                supplier_reply = {"error": str(exc)}

    if sku and (_num(mass.get("volume_m3")) is None or _num(mass.get("weight_kg")) is None):
        # 最后再试一次主数据（clarify 可能带回 sku）
        try:
            mass = collect_physical_specs(mass, product_physical_specs(sku, qty=qty) or {})
        except Exception:  # noqa: BLE001
            pass

    mass["sku"] = mass.get("sku") or sku
    mass["quantity"] = qty
    written = patch_order_specs(
        agent_id,
        order_ticket_id=order_ticket_id or (str(order.get("id")) if order else None),
        case_id=case_id,
        specs=mass,
    )
    bl = shipping_blockers_from_mass(mass, order_ticket_id=order_ticket_id)
    return with_runtime_meta(
        {
            "ok": not bl,
            "specs": mass,
            "written": written.get("written"),
            "supplier_reply_ok": bool(supplier_reply and not (supplier_reply or {}).get("error")),
            "note": "规格已写回" if not bl else "仍有缺口，见 blockers",
        },
        goal="补齐承运所需物理规格后继续询运/下物流单",
        blockers=bl,
        next_actions=["flow.request_shipping", "flow.place_logistics_order"] if not bl else ["flow.backfill_specs", "partner.dialog"],
    )
