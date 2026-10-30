# -*- coding: utf-8 -*-
"""组群竞价：采购主持聊天室；可选物流；优先国标 Group MQ；可拆单产出。"""
from __future__ import annotations

import os
import re
from typing import Any

from commerce_v2 import case_store, group_room, order_ids
from commerce_v2.ask_user import clear_ask, match_choice, parse_shortlist_ids, set_ask
from commerce_v2.buyer_path_normal import _call_logistics, _call_supplier, rewrite_demand
from commerce_v2.catalog import BUYER_PROFILES, SUPPLIERS
from commerce_v2.demand_items import enrich_brief_items, format_items_query, resolve_supplier_sku
from commerce_v2.models import Phase
from commerce_v2.protocol_bridge import discover_suppliers_for_brief
from commerce_v2.progress import ProgressFn, emit as prog
from commerce_v2.widgets import attach_pending, shortlist_widget


def _control_phrase(text: str) -> bool:
    t = text or ""
    return any(k in t for k in ("组群", "竞价", "确认", "取消", "采纳方案", "续跑"))


def _demand_corpus(case: dict[str, Any], text: str = "") -> str:
    brief = case.get("brief") or {}
    parts = [
        case.get("group_demand_text") or "",
        brief.get("raw") or "",
        brief.get("rewritten_query") or "",
        case.get("rewritten_query") or "",
        "" if _control_phrase(text) else (text or ""),
    ]
    # 选最长非控制语料，避免「我要组群竞价」覆盖真实需求
    corpus = max(parts, key=lambda s: len(str(s).strip()) if not _control_phrase(str(s)) else 0)
    return str(corpus or text or "").strip()


def _ensure_brief_items(case: dict[str, Any], text: str = "") -> dict[str, Any]:
    from commerce_v2.rewrite_grounding import gather_rewrite_evidence

    brief = dict(case.get("brief") or {})
    demand = _demand_corpus(case, text)
    evidence = gather_rewrite_evidence(case.get("agent_id") or "buyer-a")
    brief = enrich_brief_items(brief, text=demand, evidence=evidence)
    if brief.get("multi") and brief.get("items"):
        brief["rewritten_query"] = format_items_query(brief["items"]) or brief.get("rewritten_query")
    case["brief"] = brief
    case["rewritten_query"] = brief.get("rewritten_query") or case.get("rewritten_query")
    if demand and not _control_phrase(demand):
        case["group_demand_text"] = demand
    return brief


def _with_logistics_candidate(case: dict[str, Any]) -> list[dict[str, Any]]:
    cands = list(case.get("candidates") or [])
    if not any((c.get("agent_id") or "") == "logistics" for c in cands):
        cands.append(
            {
                "agent_id": "logistics",
                "candidate_id": "logistics",
                "title": "采联物流智能体",
                "city": "全国",
                "blurb": "组群旁听 · 运力方案与到岸成本合入（国标 Group Partner）",
                "checked": True,
            }
        )
    return cands


async def enter_group_ask(case: dict[str, Any], text: str, *, progress: ProgressFn = None) -> dict[str, Any]:
    agent_id = case["agent_id"]
    await prog(progress, "组群路径 · 采购将作为主持", "think")
    if not case.get("brief"):
        # 控制语不拿来改写；优先已有案语料
        src = _demand_corpus(case, text) or text
        case["brief"] = await rewrite_demand(src, agent_id)
        case["rewritten_query"] = case["brief"]["rewritten_query"]
    brief = _ensure_brief_items(case, text)
    items = brief.get("items") or []
    if brief.get("multi"):
        await prog(
            progress,
            "多品需求已锁定：" + "、".join(f"{x.get('name')}×{x.get('qty')}" for x in items),
            "tool_done",
        )
    # 发现：按全部 SKU 并集，避免只召回坐垫厂漏掉脚轮厂
    need_rediscover = not case.get("candidates") or (
        brief.get("multi") and len([c for c in (case.get("candidates") or []) if str(c.get("agent_id", "")).startswith("supplier-")]) < 2
    )
    if need_rediscover:
        await prog(progress, "正在按全部需求行发现可入群供应（多 SKU 并集）…", "tool")
        disc = await discover_suppliers_for_brief(
            case.get("rewritten_query") or brief.get("rewritten_query") or text,
            brief=brief,
            agent_id=agent_id,
        )
        case["candidates"] = disc.get("candidates") or []
        case["discovery_meta"] = {
            "source": disc.get("source"),
            "degrade": disc.get("degrade"),
            "note": disc.get("note"),
            "meta": disc.get("meta"),
        }
        await prog(progress, f"候选 {len(case['candidates'])} 家 · 来源 {disc.get('source')}", "tool_done")
    case["candidates"] = _with_logistics_candidate(case)
    case["path"] = "group"
    case["state"] = Phase.GROUP_ASK.value
    case["conflict_signals"] = case.get("conflict_signals") or ["C5"]
    sw = shortlist_widget(case)
    sw["title"] = "组群竞价：勾选供应 + 物流，再点「确认组群竞价」"
    sw["submit_label"] = "确认组群竞价"
    sw["mode"] = "group_ask"
    sw["allow_logistics"] = True
    w2 = set_ask(
        case,
        "是否开群？（可同时勾选物流智能体入群旁听）",
        [
            {"id": "group_yes", "label": "确认组群竞价", "message": "确认进行组群竞价", "primary": True},
            {"id": "group_no", "label": "取消，回普通路径", "message": "取消组群"},
        ],
    )
    case["hitl_pending"] = {"gate": "confirm_shortlist", "phase": "group_ask"}
    case["group_ask_widget"] = sw
    demand_hint = brief.get("rewritten_query") or case.get("group_demand_text") or ""
    reply = (
        f"建议组群竞价（信号 {case.get('conflict_signals')}）。主持=本采购智能体。\n"
        f"本组需求（须全覆盖）：{demand_hint}\n"
        f"请勾选入群成员（**可选物流智能体**），点「确认组群竞价」后将打开组群聊天室，"
        f"并优先走国标 ACPs Group 通道。"
    )
    case_store.save_case(case)
    return {"reply": reply, "ui_widgets": [sw, w2], "case": case}

async def handle_group_turn(
    case: dict[str, Any], text: str, *, progress: ProgressFn = None
) -> dict[str, Any] | None:
    st = case.get("state")
    if case.get("path") != "group" and st not in (
        Phase.GROUP_ASK.value,
        Phase.GROUP_BIDDING.value,
        Phase.GROUP_DECIDE.value,
        Phase.GROUP_LOGISTICS.value,
        Phase.GROUP_TICKETS.value,
    ):
        return None

    if st == Phase.GROUP_ASK.value:
        ids = parse_shortlist_ids(text)
        if ids:
            # 规范化：保留 supplier-* 与 logistics
            case["selected"] = [x for x in ids if x.startswith("supplier-") or x == "logistics"]
            await prog(progress, f"已记录入群成员 {case['selected']}", "tool_done")
        pending = case.get("pending_choices") or {}
        ch = match_choice(text, pending.get("choices") if isinstance(pending, dict) else None)
        if "取消组群" in text or (ch and ch.get("id") == "group_no"):
            case["path"] = "normal"
            case["state"] = Phase.SHORTLIST_PENDING.value
            clear_ask(case)
            case.pop("group_room", None)
            sw = shortlist_widget(case)
            attach_pending(case, sw)
            return {"reply": "已取消组群，回到普通短名单。", "ui_widgets": [sw], "case": case}
        confirm = bool(
            (ch and ch.get("id") == "group_yes")
            or "确认进行组群竞价" in text
            or "确认组群竞价" in text
            or (ids and "确认组群" in text)
        )
        if confirm:
            if not case.get("selected"):
                case["selected"] = ids or [
                    c["agent_id"] for c in case.get("candidates") or [] if c.get("agent_id")
                ]
            # 默认带上物流，除非用户明确只勾了供应且消息里没有 logistics
            sel = list(case["selected"])
            if "logistics" not in sel and "不选物流" not in text:
                sel.append("logistics")
            case["selected"] = sel
            return await _open_group_room(case, progress=progress)
        if ids:
            w2 = set_ask(
                case,
                "成员已记录。请确认是否开群竞价：",
                [
                    {"id": "group_yes", "label": "确认组群竞价", "message": "确认进行组群竞价", "primary": True},
                    {"id": "group_no", "label": "取消，回普通路径", "message": "取消组群"},
                ],
            )
            case["hitl_pending"] = {"gate": "confirm_shortlist", "phase": "group_ask"}
            case_store.save_case(case)
            return {
                "reply": f"已记录入群成员 {case.get('selected')}。请点「确认组群竞价」打开组群聊天室。",
                "ui_widgets": [w2],
                "case": case,
            }

    if st == Phase.GROUP_BIDDING.value:
        # 卡在入群后 AIP 挂起：任意消息或自动续跑报价汇总
        await prog(progress, "组群聊天室续跑 · 主持抛需求并收报价…", "tool")
        return await _run_group_quotes_and_summary(case, progress=progress)

    if st == Phase.GROUP_DECIDE.value:
        pending = case.get("pending_choices") or {}
        ch = match_choice(text, pending.get("choices") if isinstance(pending, dict) else None)
        if ch or "确认购买" in text or "下单" in text or "采纳" in text or "拆分" in text:
            return await _apply_group_plan(case, text, ch, progress=progress)

    if st == Phase.GROUP_LOGISTICS.value:
        return await _group_logistics_finish(case, progress=progress)

    return None


async def _try_gb_group(
    case: dict[str, Any], members: list[str], *, progress: ProgressFn = None
) -> tuple[str, str | None, dict[str, Any] | None]:
    """优先国标 ACPs Group；失败返回 local_shared_context + 错误说明。"""
    try_mq = os.getenv("V2_TRY_GROUP_MQ", "1") != "0"
    if not try_mq:
        return "local_shared_context", None, None
    await prog(progress, "正在经国标 ACPs Group 建组并邀请成员…", "tool")
    try:
        from commerce.group_mq import leader_aic_for, open_group

        leader_aic = leader_aic_for(case["agent_id"])
        partners = [
            m
            for m in members
            if m != case["agent_id"] and m in ("supplier-a", "supplier-b", "supplier-c", "logistics")
        ]
        rec = await open_group(
            leader_aic=leader_aic,
            leader_agent_id=case["agent_id"],
            member_agent_ids=partners,
            invite=True,
        )
        gid = getattr(rec, "session_id", None) or getattr(rec, "group_id", None) or str(rec)
        await prog(progress, f"国标 Group 建组成功 · {gid}", "tool_done")
        detail = {
            "session_id": gid,
            "members": getattr(rec, "members", None) or partners,
            "invite_errors": getattr(rec, "invite_errors", None) or [],
        }
        return "group", None, detail
    except Exception as e:  # noqa: BLE001
        err = str(e)[:240]
        await prog(progress, f"国标 Group 暂不可用，改用共享上下文仿真：{err}", "tool_done")
        return "local_shared_context", err, None


async def _open_group_room(case: dict[str, Any], *, progress: ProgressFn = None) -> dict[str, Any]:
    clear_ask(case)
    brief = case["brief"]
    host = case["agent_id"]
    members = [host] + [m for m in (case.get("selected") or []) if m != host]
    # 供应至少一家
    suppliers = [m for m in members if m.startswith("supplier-")]
    if not suppliers:
        suppliers = [
            c["agent_id"]
            for c in case.get("candidates") or []
            if str(c.get("agent_id", "")).startswith("supplier-")
        ][:2]
        members = [host, *suppliers]
        if "logistics" in (case.get("selected") or []) or True:
            members.append("logistics")
        members = list(dict.fromkeys(members))

    room = group_room.new_room(host=host, members=members, brief=brief)
    case["group_room"] = room
    case["state"] = Phase.GROUP_BIDDING.value
    case_store.save_case(case)

    group_room.tick(room, f"采购主持 {host} 发起组群竞价", kind="host", agent_id=host)
    await prog(progress, "组群聊天室已打开 · 开始邀请成员入群", "tool")

    transport, mq_err, mq_detail = await _try_gb_group(case, members, progress=progress)
    room["transport"] = transport
    if mq_detail:
        room["group_id"] = mq_detail.get("session_id")
    if mq_err:
        room["mq_error"] = mq_err
        group_room.tick(room, f"国标 Group 回退：{mq_err[:80]}", kind="warn")

    # 入群滚动条：逐个「进入 / 连接正常」
    for mid in members:
        if mid == host:
            group_room.set_member_status(room, mid, "connected")
            group_room.tick(room, f"{group_room._title(mid)} 已在群（主持）", kind="ok", agent_id=mid)
            continue
        group_room.set_member_status(room, mid, "joining")
        group_room.tick(room, f"{group_room._title(mid)} 正在进入组群…", kind="join", agent_id=mid)
        await prog(progress, f"{mid} 进入组群…", "tool")
        # 轻探活：供应初报 / 物流 schema
        try:
            # 入群握手走本地，避免 AIP 挂死导致聊天室空白
            if mid == "logistics":
                await _call_logistics(
                    host,
                    {"schema_type": "v2.logistics_schema"},
                    progress=progress,
                    action="入群握手",
                    force_local=True,
                )
            else:
                await _call_supplier(
                    host,
                    mid,
                    {"schema_type": "v2.spec_query", "sku": brief.get("sku")},
                    progress=progress,
                    action="入群握手",
                    force_local=True,
                )
            group_room.set_member_status(room, mid, "connected")
            group_room.tick(room, f"{group_room._title(mid)} 连接正常", kind="ok", agent_id=mid)
        except Exception as e:  # noqa: BLE001
            group_room.set_member_status(room, mid, "error")
            group_room.tick(room, f"{group_room._title(mid)} 连接异常：{str(e)[:60]}", kind="err", agent_id=mid)
        case_store.save_case(case)

    if not isinstance(case.get("group"), dict):
        case["group"] = {}
    case["group"]["transport"] = transport
    case["group"]["mq_error"] = mq_err
    case["group"]["group_id"] = room.get("group_id")
    case["group"]["members"] = members
    case["group"]["host"] = host
    case_store.save_case(case)
    return await _run_group_quotes_and_summary(case, progress=progress)


async def _run_group_quotes_and_summary(
    case: dict[str, Any], *, progress: ProgressFn = None
) -> dict[str, Any]:
    """入群完成后：主持抛需求 → 按行全量询价 → 物流 → 汇总（可续跑）。"""
    brief = _ensure_brief_items(case)
    host = case["agent_id"]
    room = case.get("group_room") or group_room.new_room(
        host=host, members=list((case.get("group") or {}).get("members") or []), brief=brief
    )
    case["group_room"] = room
    members = [m.get("id") if isinstance(m, dict) else m for m in (room.get("members") or [])]
    if not members:
        members = list((case.get("group") or {}).get("members") or case.get("selected") or [])
    suppliers = [m for m in members if str(m).startswith("supplier-")]
    transport = (case.get("group") or {}).get("transport") or room.get("transport") or "local_shared_context"
    # 仿真通道直接本地智力，避免跨云 AIP 卡住「群聊消息载入中」
    local = transport != "group"

    lines = list(brief.get("items") or [])
    if not lines:
        lines = [
            {
                "sku": brief.get("sku"),
                "name": brief.get("name"),
                "qty": brief.get("qty") or 1,
                "unit": brief.get("unit") or "件",
            }
        ]
    demand = (
        case.get("group_demand_text")
        or brief.get("rewritten_query")
        or format_items_query(lines)
        or f"采购 {brief.get('name')} × {brief.get('qty')}"
    )
    line_desc = "；".join(f"{x.get('name')} × {x.get('qty')}{x.get('unit') or ''}" for x in lines)
    if not (room.get("messages") or []):
        group_room.say(
            room,
            agent_id=host,
            content=(
                f"【主持】各位伙伴已入群。本组需求须全部覆盖：{demand}\n"
                f"明细：{line_desc}\n"
                f"请各供应就自己目录内有货的品类分别报价并说明优惠；物流稍后给出运力方案。"
            ),
            role="host",
        )
        case_store.save_case(case)
        await prog(progress, f"主持已抛出 {len(lines)} 行需求 · 等待供应按行报价", "tool")

    bids: list[dict[str, Any]] = list(room.get("bids") or [])
    quoted_pairs = {(b.get("supplier_agent_id"), b.get("sku")) for b in bids}
    covered_keys: set[str] = set()
    for sid in suppliers:
        group_room.tick(room, f"{group_room._title(sid)} 开始按行报价…", kind="info", agent_id=sid)
        case_store.save_case(case)
        sid_got = 0
        for line in lines:
            sku = resolve_supplier_sku(sid, line)
            if not sku:
                continue
            if (sid, sku) in quoted_pairs:
                covered_keys.add(str(line.get("prefix") or line.get("sku") or sku))
                sid_got += 1
                continue
            qty = int(line.get("qty") or brief.get("qty") or 1)
            res = await _call_supplier(
                host,
                sid,
                {"schema_type": "v2.group_bid", "sku": sku, "quantity": qty},
                progress=progress,
                action=f"组群出价·{line.get('name') or sku}",
                force_local=local,
            )
            bid = (res or {}).get("bid") or (res or {}).get("quote") or {}
            if not bid:
                continue
            bids.append(bid)
            quoted_pairs.add((sid, sku))
            covered_keys.add(str(line.get("prefix") or line.get("sku") or sku))
            sid_got += 1
            promo = bid.get("promo_reason") or ("挂牌价" if not bid.get("promo_applied") else "已套优惠")
            group_room.say(
                room,
                agent_id=sid,
                content=(
                    f"报价：{bid.get('name')} × {bid.get('qty')}，单价 {bid.get('unit_price')}，"
                    f"货款 {bid.get('goods_total')}，交期 {bid.get('lead_days')} 天。优惠：{promo}"
                ),
                role="supplier",
                meta={"bid": bid, "line": line},
            )
            promo_res = await _call_supplier(
                host,
                sid,
                {
                    "schema_type": "v2.promo_query",
                    "sku": sku,
                    "quantity": qty,
                    "question": "有什么优惠政策",
                },
                progress=progress,
                action="问优惠",
                force_local=local,
            )
            if promo_res and promo_res.get("message"):
                group_room.say(room, agent_id=sid, content=str(promo_res.get("message")), role="supplier")
            room["bids"] = bids
            case_store.save_case(case)
        if sid_got:
            group_room.set_member_status(room, sid, "quoted")
            group_room.tick(room, f"{group_room._title(sid)} 已完成 {sid_got} 行报价", kind="ok", agent_id=sid)
        else:
            group_room.set_member_status(room, sid, "no_match")
            group_room.say(
                room,
                agent_id=sid,
                content="本厂目录与本次需求行无交集，跳过报价。",
                role="supplier",
            )
            group_room.tick(room, f"{group_room._title(sid)} 无匹配品类", kind="warn", agent_id=sid)
        case_store.save_case(case)

    # 缺口提示：某需求行无人报价
    missing_lines = []
    for line in lines:
        key = str(line.get("prefix") or line.get("sku") or line.get("name"))
        has = key in covered_keys or any(
            (b.get("sku") or "").startswith(str(line.get("prefix") or "___"))
            or str(line.get("name") or "")[:2] in str(b.get("name") or "")
            for b in bids
        )
        if not has:
            missing_lines.append(line)
    if missing_lines:
        miss_txt = "、".join(f"{x.get('name')}×{x.get('qty')}" for x in missing_lines)
        group_room.say(
            room,
            agent_id=host,
            content=f"【主持提醒】以下需求行尚未拿到报价：{miss_txt}。请确认入群供应是否覆盖全部品类。",
            role="host",
        )
        await prog(progress, f"⚠ 需求漏项未报价：{miss_txt}", "tool")

    scheme = room.get("logistics_scheme")
    if "logistics" in members and not scheme:
        group_room.tick(room, "物流智能体开始给出运力方案…", kind="info", agent_id="logistics")
        case_store.save_case(case)
        await prog(progress, "供应报价齐 · 物流合入方案", "tool")
        # 多品：规格摘要拼全部行；起运取首个有报价供应
        sid0 = next((b.get("supplier_agent_id") for b in bids if b.get("supplier_agent_id")), None) or (
            suppliers[0] if suppliers else "supplier-a"
        )
        sku0 = (bids[0].get("sku") if bids else None) or brief.get("sku")
        spec = await _call_supplier(
            host,
            sid0,
            {"schema_type": "v2.spec_query", "sku": sku0},
            progress=progress,
            action="规格/起运",
            force_local=local,
        )
        fields = {
            "goods_spec": line_desc or str((spec or {}).get("spec") or brief.get("name")),
            "chargeable_qty": sum(int(x.get("qty") or 0) for x in lines) or brief.get("qty"),
            "origin": (spec or {}).get("ship_from") or SUPPLIERS.get(sid0, {}).get("city"),
            "destination": (BUYER_PROFILES.get(host) or {}).get("destination"),
            "ship_date": f"{(spec or {}).get('lead_days') or 5}天后可出库",
        }
        scheme_res = await _call_logistics(
            host,
            {"schema_type": "v2.logistics_quote", **fields},
            progress=progress,
            action="运力方案",
            force_local=local,
        )
        scheme = (scheme_res or {}).get("scheme") or scheme_res or {}
        room["logistics_scheme"] = scheme
        group_room.say(
            room,
            agent_id="logistics",
            content=(
                f"物流方案：{fields.get('origin')}→{fields.get('destination')}，"
                f"运费 {scheme.get('shipping_cost') or scheme.get('fee') or '—'}，"
                f"ETA {scheme.get('eta_days') or '—'} 天。"
                f"{(' 说明：' + str(scheme.get('note'))) if scheme.get('note') else ''}"
            ),
            role="logistics",
            meta={"scheme": scheme, "fields": fields},
        )
        group_room.set_member_status(room, "logistics", "quoted")
        group_room.tick(room, "物流智能体已提交方案", kind="ok", agent_id="logistics")
        if not isinstance(case.get("group"), dict):
            case["group"] = {}
        case["group"]["logistics_fields"] = fields
        case_store.save_case(case)

    summary = group_room.build_summary(
        brief=brief,
        bids=bids,
        logistics_scheme=scheme if isinstance(scheme, dict) else None,
        demand_text=str(case.get("group_demand_text") or demand),
    )
    room["bids"] = bids
    room["summary"] = summary
    room["status"] = "review"
    room["transport"] = transport
    cover_note = (
        "全部品类已覆盖，可拆单一次下齐。"
        if summary.get("covers_all")
        else f"仍有缺口：{'、'.join(summary.get('missing') or []) or '请检查入群名单'}。"
    )
    group_room.say(
        room,
        agent_id=host,
        content=(
            f"【主持汇总】{summary.get('narrative')}\n"
            f"{cover_note}\n"
            f"请选择下方方案（多品请优先点「全量覆盖」拆单）。"
        ),
        role="host",
        meta={"summary": summary},
    )
    group_room.tick(room, "主持已汇总 · 等待你确认方案", kind="host", agent_id=host)
    case["group"] = {
        **(case.get("group") or {}),
        "host": host,
        "members": members,
        "transport": transport,
        "bids": bids,
        "logistics_joined": "logistics" in members,
    }
    case["bargain_quotes"] = bids
    case["state"] = Phase.GROUP_DECIDE.value

    choices = []
    for p in summary.get("plans") or []:
        choices.append(
            {
                "id": p["id"],
                "label": p["label"] + (f" · 合计约 {p.get('total')}" if p.get("total") is not None else ""),
                "message": f"组群采纳方案：{p['id']}",
                "primary": bool(p.get("primary")),
            }
        )
    if not choices and bids:
        sid = bids[0].get("supplier_agent_id")
        choices.append(
            {
                "id": f"gorder_{sid}",
                "label": f"与 {sid} 下单",
                "message": f"组群决断：与{sid}下单",
                "primary": True,
            }
        )
    w = set_ask(case, "组群聊天室已汇总，请点选采购方案：", choices)
    case_store.save_case(case)
    await prog(progress, "组群聊天室汇总完成 · 请在置顶聊天室点选方案", "tool_done")
    reply = (
        f"组群聊天室已就绪（transport={transport}）。\n"
        f"{summary.get('narrative')}\n请在置顶组群聊天室点选方案。"
    )
    return {
        "reply": reply,
        "ui_widgets": [w],
        "case": case,
        "group_room": room,
        "open_group_room": True,
    }


async def _apply_group_plan(
    case: dict[str, Any], text: str, ch: dict | None, *, progress: ProgressFn = None
) -> dict[str, Any]:
    room = case.get("group_room") or {}
    summary = (room.get("summary") or {}) if isinstance(room, dict) else {}
    plans = {p["id"]: p for p in (summary.get("plans") or []) if p.get("id")}
    plan = None
    cid = (ch or {}).get("id") if ch else None
    if cid and cid in plans:
        plan = plans[cid]
    elif "拆分" in text and "plan_split" in plans:
        plan = plans["plan_split"]
    elif cid == "plan_best" or "最优" in text or "采纳" in text:
        plan = plans.get("plan_best") or (summary.get("plans") or [None])[0]
    elif cid and str(cid).startswith("gorder_"):
        sid = cid.split("_", 1)[1]
        plan = {
            "id": cid,
            "kind": "single",
            "lines": [
                {
                    "supplier_id": sid,
                    "sku": case["brief"].get("sku"),
                    "name": case["brief"].get("name"),
                    "qty": case["brief"].get("qty"),
                    "unit_price": next(
                        (b.get("unit_price") for b in (room.get("bids") or []) if b.get("supplier_agent_id") == sid),
                        None,
                    ),
                    "goods_total": next(
                        (b.get("goods_total") for b in (room.get("bids") or []) if b.get("supplier_agent_id") == sid),
                        None,
                    ),
                }
            ],
        }
    else:
        m = re.search(r"与(supplier-[a-c])下单", text)
        if m:
            return await _decide_and_invite_logistics(case, text, {"id": f"gorder_{m.group(1)}"}, progress=progress)
        plan = plans.get("plan_best") or (summary.get("plans") or [None])[0]

    if not plan or not plan.get("lines"):
        return await _decide_and_invite_logistics(case, text, ch, progress=progress)

    await prog(progress, f"采纳组群方案 {plan.get('id')} · 正在生成工单…", "tool")
    created_orders: list[dict[str, Any]] = []
    created_logs: list[dict[str, Any]] = []
    from commerce_v2 import order_sync

    fields_base = (case.get("group") or {}).get("logistics_fields") or {}
    for line in plan["lines"]:
        sid = line["supplier_id"]
        sku = line.get("sku") or case["brief"]["sku"]
        qty = int(line.get("qty") or case["brief"]["qty"])
        # 成交核算
        res = await _call_supplier(
            case["agent_id"],
            sid,
            {"schema_type": "v2.bargain", "sku": sku, "quantity": qty},
            progress=progress,
            action="成交核算",
        )
        q = (res or {}).get("quote") or {}
        oid = order_ids.new_order_id(case["case_id"], sid, sku)
        order = {
            "order_id": oid,
            "case_id": case["case_id"],
            "buyer_id": case["agent_id"],
            "supplier_id": sid,
            "sku": sku,
            "name": q.get("name") or line.get("name"),
            "qty": qty,
            "unit_price": q.get("unit_price") or line.get("unit_price"),
            "goods_total": q.get("goods_total") or line.get("goods_total"),
            "title": f"组群货单 · {q.get('name') or line.get('name')} × {qty} · {sid}",
            "buyer_ack": False,
            "supplier_ack": False,
            "effective": False,
            "place_order": "on",
        }
        order_ids.put_order(order)
        await _call_supplier(
            case["agent_id"],
            sid,
            {"schema_type": "v2.place_order", "place_order": "on", "order_id": oid, "order": order, "sku": sku, "quantity": qty},
            progress=progress,
            action="place_order(on)",
        )
        order_sync.push_order_to(sid, order, require_place_on=True)
        created_orders.append(order)
        group_room.say(
            case["group_room"],
            agent_id=case["agent_id"],
            content=f"已调用 {sid}.place_order(on)，货单 `{oid}` 待双方确认。",
            role="host",
        )

        # 每份货单一张物流单
        lid = order_ids.new_logistics_id(oid)
        fields = {
            **fields_base,
            "chargeable_qty": qty,
            "goods_spec": str(order.get("name")),
            "origin": fields_base.get("origin") or SUPPLIERS.get(sid, {}).get("city"),
            "destination": fields_base.get("destination")
            or (BUYER_PROFILES.get(case["agent_id"]) or {}).get("destination"),
        }
        scheme_res = await _call_logistics(
            case["agent_id"],
            {"schema_type": "v2.logistics_quote", **fields},
            progress=progress,
            action="拆单运力",
        )
        row = {
            "logistics_id": lid,
            "order_id": oid,
            "buyer_id": case["agent_id"],
            "supplier_id": sid,
            "title": f"组群物流单 · {fields.get('origin')}→{fields.get('destination')} · {sid}",
            "scheme": (scheme_res or {}).get("scheme"),
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
            action="物流下单",
        )
        order_sync.push_logistics_to("logistics", row)
        created_logs.append(row)

    case["order"] = created_orders[0]
    case["order_id"] = created_orders[0]["order_id"]
    case["orders"] = created_orders
    case["logistics"] = created_logs[0] if created_logs else None
    case["logistics_id"] = created_logs[0]["logistics_id"] if created_logs else None
    case["logistics_list"] = created_logs
    case["state"] = Phase.GROUP_TICKETS.value
    if case.get("group_room"):
        case["group_room"]["status"] = "closed"
        group_room.tick(
            case["group_room"],
            f"已产出货单 {len(created_orders)} + 物流 {len(created_logs)}，请各方 Gate 确认",
            kind="ok",
        )
    clear_ask(case)
    case_store.save_case(case)
    oids = ", ".join(f"`{o['order_id']}`" for o in created_orders)
    lids = ", ".join(f"`{r['logistics_id']}`" for r in created_logs)
    reply = (
        f"组群方案 `{plan.get('id')}` 已落地：货单 {oids}；物流 {lids}。\n"
        f"请到工单页由采购/供应/物流各方确认。"
    )
    return {"reply": reply, "ui_widgets": [], "case": case, "open_group_room": True}


async def _decide_and_invite_logistics(
    case: dict[str, Any], text: str, ch: dict | None, *, progress: ProgressFn = None
) -> dict[str, Any]:
    sid = None
    if ch and str(ch.get("id", "")).startswith("gorder_"):
        sid = ch["id"].split("_", 1)[1]
    m = re.search(r"与(supplier-[a-c])下单", text)
    if m:
        sid = m.group(1)
    if not sid:
        sid = next(
            (x for x in (case.get("selected") or []) if str(x).startswith("supplier-")),
            "supplier-a",
        )
    # 复用方案落地：构造单行 plan
    bids = ((case.get("group_room") or {}).get("bids") or case.get("bargain_quotes") or [])
    b = next((x for x in bids if x.get("supplier_agent_id") == sid), {}) or {}
    fake = {
        "id": f"gorder_{sid}",
        "kind": "single",
        "lines": [
            {
                "supplier_id": sid,
                "sku": case["brief"].get("sku"),
                "name": b.get("name") or case["brief"].get("name"),
                "qty": case["brief"].get("qty"),
                "unit_price": b.get("unit_price"),
                "goods_total": b.get("goods_total"),
            }
        ],
    }
    case.setdefault("group_room", {}).setdefault("summary", {})["plans"] = [fake]
    return await _apply_group_plan(case, text, {"id": fake["id"]}, progress=progress)


async def _group_logistics_finish(case: dict[str, Any], *, progress: ProgressFn = None) -> dict[str, Any]:
    # 兼容旧话术「完成组群物流」
    if case.get("order") and not case.get("logistics_id"):
        return await _apply_group_plan(
            case,
            "采纳最优",
            {"id": "plan_best"},
            progress=progress,
        )
    reply = f"组群工单已在案：货单 `{case.get('order_id')}` 物流 `{case.get('logistics_id')}`。"
    return {"reply": reply, "ui_widgets": [], "case": case}
