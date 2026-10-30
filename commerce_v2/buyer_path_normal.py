# -*- coding: utf-8 -*-
"""普通采购十点路径（确定性编排，保证交互可测）。"""
from __future__ import annotations

import os
import re
from typing import Any

from commerce_v2 import case_store, order_ids
from commerce_v2.ask_user import clear_ask, match_choice, parse_shortlist_ids, set_ask
from commerce_v2.catalog import BUYER_PROFILES, SUPPLIERS
from commerce_v2.llm_rewrite import rewrite_demand_llm
from commerce_v2.models import Phase
from commerce_v2.protocol_bridge import aip_call, discover_suppliers_for_brief, extract_business
from commerce_v2.widgets import attach_pending, shortlist_widget

# 同进程智力回退（RPC 不可达时仍可测交互）
from commerce_v2 import partner_logistics as plog
from commerce_v2 import partner_supplier as psup
from commerce_v2.progress import ProgressFn, emit as prog


def _profile(agent_id: str) -> dict[str, Any]:
    return BUYER_PROFILES.get(agent_id) or BUYER_PROFILES["buyer-a"]


async def rewrite_demand(text: str, agent_id: str) -> dict[str, Any]:
    """需求改写只走 LLM（硬规则已删除）。"""
    return await rewrite_demand_llm(text, agent_id)


def _leader_aic(agent_id: str) -> str:
    if agent_id == "buyer-b":
        return os.getenv("BUYER_B_AIC", "buyer-b-local-aic")
    return os.getenv("BUYER_A_AIC", "buyer-a-local-aic")


async def _call_supplier(
    agent_id: str,
    sid: str,
    envelope: dict[str, Any],
    *,
    progress: ProgressFn = None,
    action: str = "初报",
    force_local: bool = False,
) -> dict[str, Any]:
    import asyncio

    from commerce_v2.catalog import _rpc

    url = _rpc(sid)
    aic_env = {"supplier-a": "SUPPLIER_A_AIC", "supplier-b": "SUPPLIER_B_AIC", "supplier-c": "SUPPLIER_C_AIC"}
    aic = os.getenv(aic_env.get(sid, ""), f"{sid}-local-aic")
    schema = str(envelope.get("schema_type") or "")
    local = force_local or os.getenv("V2_LOCAL_PARTNERS", "1") == "1"
    if local:
        await prog(progress, f"正在调用本地供应智力 · {sid} · {action}（{schema or 'envelope'}）", "tool")
        return psup.handle_envelope(sid, envelope)
    await prog(progress, f"正在经 AIP 连接 {sid}（{url}）…", "tool")
    await prog(progress, f"正在调用工具 · {sid}.{action}", "tool")
    try:
        timeout = float(os.getenv("V2_AIP_TIMEOUT_SEC") or "8")
        raw = await asyncio.wait_for(
            aip_call(
                url,
                aic,
                envelope,
                leader_aic=_leader_aic(agent_id),
                session_id=f"v2-{agent_id}-{sid}-{envelope.get('business_id') or 'x'}",
                local_agent_id=agent_id,
            ),
            timeout=max(3.0, timeout),
        )
        biz = extract_business(raw)
        if biz:
            await prog(progress, f"{sid} AIP 回执成功 · {action}", "tool_done")
            return biz
        await prog(progress, f"{sid} AIP 无业务包，回退本地智力 · {action}", "tool_done")
        return psup.handle_envelope(sid, envelope)
    except Exception as e:  # noqa: BLE001
        await prog(progress, f"{sid} AIP 失败/超时，回退本地智力：{str(e)[:120]}", "tool_done")
        return psup.handle_envelope(sid, envelope)


async def _call_logistics(
    agent_id: str,
    envelope: dict[str, Any],
    *,
    progress: ProgressFn = None,
    action: str = "运力询价",
    force_local: bool = False,
) -> dict[str, Any]:
    import asyncio

    schema = str(envelope.get("schema_type") or "")
    if force_local or os.getenv("V2_LOCAL_PARTNERS", "1") == "1":
        await prog(progress, f"正在调用本地物流智力 · {action}（{schema}）", "tool")
        return plog.handle_envelope("logistics", envelope)
    from commerce_v2.catalog import _rpc

    await prog(progress, "正在经 AIP 连接物流智能体…", "tool")
    await prog(progress, f"正在调用工具 · logistics.{action}", "tool")
    try:
        timeout = float(os.getenv("V2_AIP_TIMEOUT_SEC") or "8")
        raw = await asyncio.wait_for(
            aip_call(
                _rpc("logistics"),
                os.getenv("LOGISTICS_AIC", "logistics-local-aic"),
                envelope,
                leader_aic=_leader_aic(agent_id),
                session_id=f"v2-{agent_id}-logistics-{envelope.get('business_id') or 'x'}",
                local_agent_id=agent_id,
            ),
            timeout=max(3.0, timeout),
        )
        biz = extract_business(raw)
        if biz:
            await prog(progress, f"物流 AIP 回执成功 · {action}", "tool_done")
            return biz
        await prog(progress, f"物流 AIP 无业务包，回退本地 · {action}", "tool_done")
        return plog.handle_envelope("logistics", envelope)
    except Exception as e:  # noqa: BLE001
        await prog(progress, f"物流 AIP 失败/超时，回退本地：{str(e)[:120]}", "tool_done")
        return plog.handle_envelope("logistics", envelope)


def _quotes_table(quotes: list[dict[str, Any]]) -> str:
    lines = [
        "| 供应 | 品名 | 数量 | 单价 | 货款 | 交期 | 优惠说明 |",
        "|---|---|---|---|---|---|---|",
    ]
    for q in quotes:
        promo = q.get("promo_reason") or ("已套用优惠" if q.get("promo_applied") else "挂牌价")
        lines.append(
            f"| {q.get('supplier_agent_id')} | {q.get('name')} | {q.get('qty')} | "
            f"{q.get('unit_price')} | {q.get('goods_total')} | {q.get('lead_days')}天 | "
            f"{promo} |"
        )
    return "\n".join(lines)


async def handle_turn(case: dict[str, Any], text: str, *, progress: ProgressFn = None) -> dict[str, Any]:
    """处理一轮用户输入，返回 {reply, ui_widgets, case}。"""
    agent_id = case["agent_id"]
    st = case.get("state") or Phase.IDLE.value
    widgets: list[dict[str, Any]] = []
    reply = ""

    # —— 断点回灌：短名单 ——
    ids = parse_shortlist_ids(text)
    if ids and st == Phase.SHORTLIST_PENDING.value:
        await prog(progress, f"已确认短名单：{', '.join(ids)}", "tool_done")
        await prog(progress, "准备并行初报（未确认前不会发 RFQ，本步已获准）…", "tool")
        case["selected"] = ids
        case["state"] = Phase.RFQ_DONE.value
        clear_ask(case)
        quotes = []
        brief = case["brief"]
        for sid in ids:
            env = {
                "schema_type": "v2.initial_quote",
                "sku": brief["sku"],
                "quantity": brief["qty"],
                "business_id": case["case_id"],
            }
            res = await _call_supplier(agent_id, sid, env, progress=progress, action="初报")
            q = (res or {}).get("quote")
            if q:
                quotes.append(q)
        case["quotes"] = quotes
        case["state"] = Phase.BARGAIN_ASK.value
        await prog(progress, f"初报汇总完成 · {len(quotes)} 家回执", "tool_done")
        w = set_ask(
            case,
            "初报已汇总。是否直接向各供应智能体询问「有什么优惠政策」？（断点②）",
            [
                {"id": "bargain_yes", "label": "询问优惠政策", "message": "请帮我议价，询问优惠政策", "primary": True},
                {"id": "bargain_no", "label": "不问优惠，直接选买法", "message": "不议价，直接进入购买决策"},
            ],
        )
        widgets = [w]
        reply = f"已对 {', '.join(ids)} 完成并行初报：\n{_quotes_table(quotes)}\n\n请点选是否向供应询问优惠政策。"
        case_store.append_history(case, "assistant", reply)
        case_store.save_case(case)
        return {"reply": reply, "ui_widgets": widgets, "case": case}

    # —— AskUser 选项 ——
    pending = case.get("pending_choices") or {}
    ch = match_choice(text, pending.get("choices"))
    if ch:
        cid = ch.get("id")
        clear_ask(case)
        if st == Phase.BARGAIN_ASK.value:
            if cid == "bargain_yes":
                await prog(progress, "用户选择议价 · 直接询问各供应「有什么优惠政策」…", "tool")
                brief = case["brief"]
                demand_qty = int(brief.get("qty") or 0)
                promo_lines: list[str] = []
                bqs: list[dict[str, Any]] = []
                for sid in case.get("selected") or []:
                    promo_res = await _call_supplier(
                        agent_id,
                        sid,
                        {
                            "schema_type": "v2.promo_query",
                            "sku": brief.get("sku"),
                            "question": "有什么优惠政策",
                            "business_id": case["case_id"],
                        },
                        progress=progress,
                        action="询问优惠政策",
                    )
                    msg = (promo_res or {}).get("message") or f"{sid}：未返回优惠说明"
                    promo_lines.append(f"- {msg}")
                    # 再按真实需求量套用已公示优惠报价（不再虚增数量试探）
                    res = await _call_supplier(
                        agent_id,
                        sid,
                        {
                            "schema_type": "v2.bargain",
                            "sku": brief["sku"],
                            "quantity": demand_qty,
                            "business_id": case["case_id"],
                        },
                        progress=progress,
                        action="按需求量套用优惠报价",
                    )
                    q = (res or {}).get("quote")
                    if q:
                        bqs.append(q)
                case["promo_answers"] = promo_lines
                case["bargain_quotes"] = bqs
                case["state"] = Phase.BUY_ASK.value
                await prog(progress, "优惠政策与议价回执已齐 · 生成买法建议", "tool_done")
                reply = (
                    "已直接询问各供应智能体「有什么优惠政策」：\n"
                    + "\n".join(promo_lines)
                    + f"\n\n按你的真实需求量 {demand_qty} 套用优惠后的报价：\n{_quotes_table(bqs)}\n\n"
                    + _buy_advice(case)
                )
                w = _buy_choices(case)
                widgets = [w]
            else:
                await prog(progress, "跳过议价 · 进入买法决策", "tool")
                case["state"] = Phase.BUY_ASK.value
                reply = "跳过议价。请决定怎么买：\n" + _buy_advice(case)
                w = _buy_choices(case)
                widgets = [w]
            case_store.append_history(case, "assistant", reply)
            case_store.save_case(case)
            return {"reply": reply, "ui_widgets": widgets, "case": case}

        if st == Phase.BUY_ASK.value:
            return await _apply_buy_choice(case, cid or "", text, progress=progress)

        if st == Phase.LOGISTICS_HINT.value and cid == "logistics_go":
            return await _start_logistics(case, progress=progress)

        if st == Phase.GROUP_ASK.value:
            pass

    # —— 状态查询：确认了吗 ——
    if any(k in text for k in ("确认了吗", "是否确认", "生效了吗", "ACTIVE")):
        await prog(progress, "正在读取共享订单确认态（Gate 字段）…", "tool")
        return _status_reply(case)

    # —— 新需求 / IDLE ——
    if st in (Phase.IDLE.value, Phase.ACTIVE.value) or "采购" in text or "买" in text or "脚轮" in text:
        if st == Phase.ACTIVE.value and "采购" not in text and "买" not in text:
            return _status_reply(case)
        await prog(progress, "正在查阅采购商家画像与本厂库存物料…", "tool")
        from commerce_v2.rewrite_grounding import gather_rewrite_evidence

        evidence = gather_rewrite_evidence(agent_id)
        inv_n = len(evidence.get("buyer_inventory") or [])
        cat_n = len(evidence.get("supplier_catalog") or [])
        await prog(
            progress,
            f"已加载画像 · 本厂物料 {inv_n} 项 · 供应目录 {cat_n} 行",
            "tool_done",
        )
        await prog(progress, "正在依据画像/库存/目录，用大模型消歧并改写需求…", "think")
        brief = await rewrite_demand(text, agent_id)
        case["brief"] = brief
        case["rewritten_query"] = brief["rewritten_query"]
        case["path"] = "normal"
        engine = brief.get("rewrite_engine") or "llm"
        used = brief.get("evidence_used") or []
        used_txt = ("；依据：" + "、".join(str(x) for x in used[:3])) if used else ""
        await prog(
            progress,
            f"需求改写完成（{engine}）：{brief['rewritten_query']}{used_txt}",
            "tool_done",
        )
        if brief.get("hint"):
            await prog(progress, f"改写依据：{brief['hint']}", "tool_done")
        await prog(progress, "正在连接梧桐平台 · 智能体发现（ADP）…", "tool")
        disc = await discover_suppliers_for_brief(brief["rewritten_query"], brief=brief, agent_id=agent_id)
        case["candidates"] = disc.get("candidates") or []
        case["discovery_meta"] = {
            "source": disc.get("source"),
            "degrade": disc.get("degrade"),
            "error": disc.get("error"),
            "meta": disc.get("meta") or {},
            "note": disc.get("note"),
            "ui_candidates": case["candidates"],
        }
        src = disc.get("source")
        meta = disc.get("meta") or {}
        url_hint = meta.get("discovery_url") or os.getenv("ACPS_DISCOVERY_URL") or ""
        if url_hint:
            await prog(progress, f"梧桐发现入口：{url_hint}", "tool")
        item_n = len(brief.get("items") or [])
        if item_n >= 2:
            await prog(
                progress,
                "多品需求 "
                + "、".join(f"{x.get('name')}×{x.get('qty')}" for x in brief.get("items") or [])
                + " · 发现按 SKU 并集召回",
                "tool_done",
            )
        if disc.get("degrade") or src == "local_directory":
            err = disc.get("error") or meta.get("platform_error") or "empty"
            sku_hint = ",".join(
                str(x.get("sku")) for x in (brief.get("items") or []) if x.get("sku")
            ) or brief.get("sku")
            await prog(
                progress,
                f"平台发现未命中/降级 · {src} · 原因：{str(err)[:120]} · 本地黄页按 SKU={sku_hint} 过滤",
                "tool_done",
            )
        else:
            titles = "、".join(
                str(c.get("title") or c.get("agent_id")) for c in (case["candidates"] or [])[:3]
            )
            await prog(
                progress,
                f"梧桐 ADP 命中 · 来源 {src} · {len(case['candidates'])} 家：{titles}",
                "tool_done",
            )
        await prog(progress, "正在分析冲突信号（规格/价格口径）…", "tool")
        signals = _conflict_signals(case)
        case["conflict_signals"] = signals
        if signals:
            await prog(progress, f"检测到冲突信号 {', '.join(signals)}", "tool_done")
        else:
            await prog(progress, "未发现硬冲突信号", "tool_done")
        case["state"] = Phase.SHORTLIST_PENDING.value
        sw = shortlist_widget(case)
        attach_pending(case, sw)
        widgets = [sw]
        extra = ""
        if signals:
            extra = (
                f"\n\n检测到冲突信号 {', '.join(signals)}。"
                f"若要组群竞价，请另发：「我要组群竞价」。否则请先勾选供应确认交互。"
            )
        reply = (
            f"已理解并改写需求：{brief['rewritten_query']}（{brief['hint']}）\n"
            f"发现来源：{disc.get('source')}，候选 {len(case['candidates'])} 家。"
            f"{extra}\n请在短名单中勾选并「确认并询价」（断点①）。"
        )
        await prog(progress, "等待你确认短名单（断点①）· 确认前不发 RFQ", "ask")
        case_store.append_history(case, "user", text)
        case_store.append_history(case, "assistant", reply)
        case_store.save_case(case)
        return {"reply": reply, "ui_widgets": widgets, "case": case, "rpc_quotes_sent": 0}

    if "组群" in text or "竞价" in text:
        from commerce_v2.buyer_path_group import enter_group_ask

        await prog(progress, "正在进入组群竞价路径…", "tool")
        return await enter_group_ask(case, text, progress=progress)

    if st == Phase.LOGISTICS_HINT.value and ("物流" in text or "运" in text):
        return await _start_logistics(case, progress=progress)

    reply = f"当前状态 {st}。可继续点选上方按钮，或询问订单是否生效。"
    return {"reply": reply, "ui_widgets": widgets, "case": case}


def _buy_advice(case: dict[str, Any]) -> str:
    brief = case.get("brief") or {}
    qty = int(brief.get("qty") or 0)
    quotes = case.get("bargain_quotes") or case.get("quotes") or []
    if not quotes:
        return "暂无报价。"
    best = min(quotes, key=lambda q: float(q.get("unit_price") or 1e9))
    sid = best.get("supplier_agent_id")
    promo = None
    sku = brief.get("sku")
    if sid in SUPPLIERS and sku in SUPPLIERS[sid]["skus"]:
        promo = SUPPLIERS[sid]["skus"][sku].get("promo")
    tip = f"建议优先考虑 {sid}（单价 {best.get('unit_price')}）。"
    if promo and promo.get("type") == "qty_discount" and qty < int(promo.get("min_qty") or 0):
        tip += f" 当前 {qty} 未达满 {promo.get('min_qty')} 件九折；可加到 {promo.get('min_qty')} 套享优惠。"
    return tip


def _buy_choices(case: dict[str, Any]) -> dict[str, Any]:
    brief = case.get("brief") or {}
    qty = int(brief.get("qty") or 0)
    quotes = case.get("bargain_quotes") or case.get("quotes") or []
    best = min(quotes, key=lambda q: float(q.get("unit_price") or 1e9)) if quotes else {}
    sid = best.get("supplier_agent_id") or (case.get("selected") or ["supplier-a"])[0]
    choices = [
        {
            "id": f"buy_{sid}_{qty}",
            "label": f"仍下 {qty} 套 · 只向 {sid} 下单",
            "message": f"确认购买：供应商{sid} 数量{qty}",
            "primary": True,
        },
        {
            "id": f"buy_{sid}_500",
            "label": f"加到 500 套享满减 · 只向 {sid} 下单",
            "message": f"确认购买：供应商{sid} 数量500",
        },
        {"id": "buy_other", "label": "Other（我补充说明）", "message": "Other：我自己说明怎么买"},
    ]
    return set_ask(case, "请决定怎么买（断点③）", choices)


async def _apply_buy_choice(
    case: dict[str, Any], cid: str, text: str, *, progress: ProgressFn = None
) -> dict[str, Any]:
    brief = case["brief"]
    sid = (case.get("selected") or ["supplier-a"])[0]
    qty = int(brief["qty"])
    m = re.search(r"供应商(supplier-[a-c]).*?数量(\d+)", text)
    if m:
        sid, qty = m.group(1), int(m.group(2))
    elif cid.startswith("buy_"):
        parts = cid.split("_")
        if len(parts) >= 3:
            sid = parts[1]
            if parts[2].isdigit():
                qty = int(parts[2])
    if cid == "buy_other" or text.startswith("Other"):
        reply = "请直接发送：确认购买：供应商supplier-a 数量500"
        w = _buy_choices(case)
        return {"reply": reply, "ui_widgets": [w], "case": case}

    await prog(progress, f"正在锁定买法 · {sid} × {qty}", "tool")
    quotes = case.get("bargain_quotes") or case.get("quotes") or []
    q = next((x for x in quotes if x.get("supplier_agent_id") == sid), None)
    if not q:
        res = await _call_supplier(
            case["agent_id"],
            sid,
            {"schema_type": "v2.bargain", "sku": brief["sku"], "quantity": qty},
            progress=progress,
            action="按买法重报价",
        )
        q = (res or {}).get("quote") or {}
    res2 = await _call_supplier(
        case["agent_id"],
        sid,
        {"schema_type": "v2.bargain", "sku": brief["sku"], "quantity": qty},
        progress=progress,
        action="成交价核算",
    )
    q = (res2 or {}).get("quote") or q
    oid = order_ids.new_order_id(case["case_id"], sid, brief["sku"])
    # 用户明确下单 → place_order=on，才调用供应商工具落单
    order = {
        "order_id": oid,
        "case_id": case["case_id"],
        "buyer_id": case["agent_id"],
        "supplier_id": sid,
        "sku": brief["sku"],
        "name": q.get("name") or brief["name"],
        "qty": qty,
        "unit_price": q.get("unit_price"),
        "goods_total": q.get("goods_total"),
        "title": f"货单 · {q.get('name')} × {qty} · {sid}",
        "buyer_ack": False,
        "supplier_ack": False,
        "effective": False,
        "place_order": "on",
    }
    order_ids.put_order(order)
    await prog(progress, f"用户已明确下单 · 调用 {sid}.place_order（place_order=on）…", "tool")
    placed = await _call_supplier(
        case["agent_id"],
        sid,
        {
            "schema_type": "v2.place_order",
            "place_order": "on",
            "order_id": oid,
            "sku": brief["sku"],
            "quantity": qty,
            "order": order,
        },
        progress=progress,
        action="place_order(on)",
    )
    if placed and placed.get("ok") is False:
        reply = f"供应商工具 place_order 拒绝：{placed.get('error') or '未知原因'}。请重试明确下单。"
        case_store.append_history(case, "assistant", reply)
        case_store.save_case(case)
        return {"reply": reply, "ui_widgets": [], "case": case}
    # 双云兜底：HTTP 再推一次（仍带 place_order=on）
    from commerce_v2 import order_sync

    order_sync.push_order_to(sid, order, require_place_on=True)
    case["order"] = order
    case["order_id"] = oid
    case["buyer_order_ack"] = False
    case["supplier_order_ack"] = False
    case["state"] = Phase.ORDER_DRAFT.value
    clear_ask(case)
    await prog(progress, "供应商工具已接单 · 等待双边 Gate 确认", "tool_done")
    reply = (
        f"已明确下单：调用供应商工具 `place_order`（place_order=on），共享订单 `{oid}`。\n"
        f"效力以双方工单确认准。请到工单页点「确认订单」；供应侧亦需确认。"
    )
    case_store.append_history(case, "assistant", reply)
    case_store.save_case(case)
    return {"reply": reply, "ui_widgets": [], "case": case}


async def _start_logistics(case: dict[str, Any], *, progress: ProgressFn = None) -> dict[str, Any]:
    if case.get("state") not in (Phase.ORDER_EFFECTIVE.value, Phase.LOGISTICS_HINT.value, Phase.LOGISTICS_SCHEMA.value):
        reply = "货物订单尚未双方确认生效，不能询运。请先完成工单确认。"
        return {"reply": reply, "ui_widgets": [], "case": case}
    await prog(progress, "货单已生效 · 开始询物流", "tool")
    schema = await _call_logistics(
        case["agent_id"], {"schema_type": "v2.logistics_schema"}, progress=progress, action="必填清单"
    )
    case["logistics_schema"] = schema
    case["state"] = Phase.LOGISTICS_SCHEMA.value
    order = case.get("order") or {}
    brief = case.get("brief") or {}
    sid = order.get("supplier_id")
    await prog(progress, f"正在向 {sid} 拉取规格/起运地…", "tool")
    spec_res = await _call_supplier(
        case["agent_id"],
        sid,
        {"schema_type": "v2.spec_query", "sku": brief.get("sku")},
        progress=progress,
        action="规格查询",
    )
    fields = {
        "goods_spec": str((spec_res or {}).get("spec") or order.get("name")),
        "chargeable_qty": order.get("qty") or brief.get("qty"),
        "origin": (spec_res or {}).get("ship_from") or SUPPLIERS.get(sid, {}).get("city"),
        "destination": _profile(case["agent_id"])["destination"],
        "ship_date": f"{(spec_res or {}).get('lead_days') or 5}天后可出库",
    }
    quote_env = {"schema_type": "v2.logistics_quote", **fields}
    scheme_res = await _call_logistics(
        case["agent_id"], quote_env, progress=progress, action="运力方案"
    )
    scheme = (scheme_res or {}).get("scheme") or {}
    lid = order_ids.new_logistics_id(case["order_id"])
    row = {
        "logistics_id": lid,
        "order_id": case["order_id"],
        "buyer_id": case["agent_id"],
        "supplier_id": sid,
        "title": f"物流单 · {fields.get('origin')}→{fields.get('destination')}",
        "scheme": scheme,
        "fields": fields,
        "buyer_ack": False,
        "logistics_ack": False,
        "effective": False,
    }
    order_ids.put_logistics(row)
    await _call_logistics(
        case["agent_id"],
        {"schema_type": "v2.place_logistics", "logistics_id": lid, "logistics": row},
        progress=progress,
        action="物流下单通知",
    )
    from commerce_v2 import order_sync

    order_sync.push_logistics_to("logistics", row)
    case["logistics"] = row
    case["logistics_id"] = lid
    case["state"] = Phase.LOGISTICS_PENDING.value
    clear_ask(case)
    await prog(progress, f"物流工单已生成 `{lid}` · 等待 Gate 确认", "tool_done")
    reply = (
        f"物流必填清单已对齐并补齐字段：{fields}\n"
        f"运力方案：{scheme}\n"
        f"已建物流工单 `{lid}`，请双方确认。"
    )
    case_store.append_history(case, "assistant", reply)
    case_store.save_case(case)
    return {"reply": reply, "ui_widgets": [], "case": case}


def _status_reply(case: dict[str, Any]) -> dict[str, Any]:
    oid = case.get("order_id")
    o = order_ids.get_order(oid) if oid else None
    if o:
        case["buyer_order_ack"] = bool(o.get("buyer_ack"))
        case["supplier_order_ack"] = bool(o.get("supplier_ack"))
        if o.get("effective"):
            case["state"] = Phase.ORDER_EFFECTIVE.value
            if not case.get("logistics_id"):
                case["state"] = Phase.LOGISTICS_HINT.value
                w = set_ask(
                    case,
                    "货单已双方确认生效。是否去询物流？（放行）",
                    [{"id": "logistics_go", "label": "去和物流询价下单", "message": "允许询运", "primary": True}],
                )
                reply = (
                    f"订单 `{oid}` 状态：buyer_ack={o.get('buyer_ack')} supplier_ack={o.get('supplier_ack')} "
                    f"effective=True。已生效。"
                )
                case_store.save_case(case)
                return {"reply": reply, "ui_widgets": [w], "case": case}
        reply = (
            f"订单 `{oid}`：buyer_ack={o.get('buyer_ack')} supplier_ack={o.get('supplier_ack')} "
            f"effective={o.get('effective')}。以工单字段为准，不以口头为准。"
        )
    else:
        reply = f"当前案 {case.get('case_id')} 状态 {case.get('state')}，尚无订单。"
    case_store.save_case(case)
    return {"reply": reply, "ui_widgets": [], "case": case}


def _conflict_signals(case: dict[str, Any]) -> list[str]:
    cands = case.get("candidates") or []
    brief = case.get("brief") or {}
    signals = []
    if len(cands) >= 2:
        # C2/C1 简化：多家候选且 sku 在不同家规格描述可能冲突时标 C1
        skus_have = []
        for c in cands:
            aid = c.get("agent_id")
            if aid in SUPPLIERS and brief.get("sku") in SUPPLIERS[aid]["skus"]:
                skus_have.append(SUPPLIERS[aid]["skus"][brief["sku"]]["spec"])
        if len(skus_have) >= 2 and skus_have[0] != skus_have[1]:
            signals.append("C1")
        if len(cands) >= 2:
            signals.append("C2")
    return signals
