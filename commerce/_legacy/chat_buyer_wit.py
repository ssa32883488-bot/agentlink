"""采购商A 对话：Wit + DeepSeek（OpenAI 兼容）+ 业务 Capability。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from wit import (
    AmpAccessLoggingHooks,
    OpenAIChatProvider,
    WitAgent,
    WitRuntime,
    capability,
)

from commerce import buyer_service as bs
from commerce import flow_service as fs
from commerce import procurement_case as pc
from commerce.buyer_tools.service import get_buyer_tools
from commerce.env_loader import llm_settings

RfqFn = Callable[[list[dict[str, Any]]], Awaitable[dict[str, Any]]]

# 对话会话绑定的当前采购案（进程内；多实例可改 Redis）
_ACTIVE_CASE_ID: str | None = None


_ACTIVE_THREAD_ID: str | None = None


def _set_active_thread(thread_id: str | None) -> None:
    global _ACTIVE_THREAD_ID
    _ACTIVE_THREAD_ID = thread_id


def _set_active_case(case_id: str | None, *, product_name: str | None = None) -> None:
    global _ACTIVE_CASE_ID
    _ACTIVE_CASE_ID = case_id
    get_buyer_tools().set_active_case(case_id)
    # 绑到当前对话窗，避免下一轮 flow.status 串到别的物料案
    if _ACTIVE_THREAD_ID and case_id:
        try:
            from commerce import chat_sessions as cs

            if not product_name:
                case = pc.get_case(case_id) or {}
                product_name = str((case.get("brief") or {}).get("product_name") or "") or None
            cs.bind_thread_case(_AGENT_ID, _ACTIVE_THREAD_ID, case_id, product_name=product_name)
        except Exception:  # noqa: BLE001
            pass


def _active_case_id() -> str | None:
    return _ACTIVE_CASE_ID or get_buyer_tools().active_case_id()


def _restore_case_for_thread(thread_id: str | None) -> str | None:
    """仅恢复本窗绑定案；绝不偷偷改绑到「最新一案」。"""
    global _ACTIVE_CASE_ID
    if not thread_id:
        return _active_case_id()
    from commerce import chat_sessions as cs

    bound = cs.thread_bound_case_id(_AGENT_ID, thread_id)
    if bound and pc.get_case(bound):
        _set_active_case(bound)
        return bound
    # 本窗尚无绑定：清空全局活跃案，防止脚轮旧案污染扶手对话
    _ACTIVE_CASE_ID = None
    get_buyer_tools().set_active_case(None)
    return None

_INSTRUCTIONS_TMPL = """你是「采联·{display}」智能体（Leader / 采购甲方）。你高度能干：在人类授权边界内，持续推进采购目标，直到卡住必须人确认或目标完成。

# 目标（不要背流程剧本）
默认目标链路：发现供应 → 人选短名单 → 询价/议价 → 人确认货物单生效 → 询运/人确认物流单生效。
你不是流水线脚本；工具回执里的 blockers / system_reminder / next_actions 才是当下该做什么的信号。

# 做事原则（学 Claude Code：原则驱动，禁止穷举所有 if）
1. 先读再动：对外数字与规格只来自工具回执；禁止编造价格/库存/体积/重量/优惠。
2. 失败先诊断：若询运/下物流失败或回执含 blockers，先 flow.inspect_goal 或读 system_reminder，再换战术；不要空转解释。
3. 缺数找持有方：缺体积/重量 → flow.backfill_specs（主数据或问供应）写回订单 → 再重试物流；缺报价 → 问供应；缺人选/下单确认 → 出按钮给人类。
4. 改量必须落地：人类说改为 N，flow.decide_order 必须传 quantity=N，禁止仍用初询量。
5. 初询不泄优惠：初询只展示挂牌价+规格；优惠用 negotiate，照回执讲，禁止因空字段说「没有优惠」。
6. HITL：短名单、货物下单、物流下单须人点确认；禁止替人成交、禁止自动 spawn 物流、禁止让供应代联系物流。
7. 货物流与物流流分离：默认 need_freight=false；承运由采购与物流谈。
8. 出按钮时机（套皮 Claude Code AskUserQuestion）：
   - 要出：歧义澄清、≥2 业务路径（议价/拆单/竞价/下单）、不可逆前择路、holder=人类的 blockers。
   - 不出：单步查数、已够信息、用按钮问「计划好不好/要不要继续」（那是工单确认，不是选择题）。
   - 推荐项放第一个并标「（推荐）」。

# 能力
discover.suppliers · rfq.send_batch · partner.dialog · flow.inspect_goal · flow.backfill_specs
flow.decide_order · flow.request_shipping · flow.place_logistics_order
flow.decide_auction/run_auction（仅人明确要求且同物料多家可比）
erp.* · memory.* · calc.compare_table · ui.offer_choices · flow.status / confirm_* / activate / hitl_decide

# 表达
结论一两句。报价表：`供应商|物料|数量|单价|货价|优惠说明|体积|交期`。物流表：`运费|ETA|起点|终点|体积/重量`。
工具若返回 system_reminder，优先按其缺口行动，不要对用户长篇抱怨「好笨/没参数」。
"""

_AGENT_ID = "buyer-a"
_DISPLAY = "采购商A"
_WORKSPACE = Path(__file__).resolve().parents[1] / "workspaces" / "buyer-a-wit"


def _render_instructions(display: str) -> str:
    # 勿用 str.format：提示词里常有 JSON/{脚轮,500} 等花括号，会 KeyError 导致进程起不来
    return _INSTRUCTIONS_TMPL.replace("{display}", display)


INSTRUCTIONS = _render_instructions(_DISPLAY)


def configure(*, agent_id: str = "buyer-a") -> None:
    """A/B 同构 Wit 运行时：仅 agent_id / 工作区 / 展示名不同。"""
    global _AGENT_ID, _DISPLAY, _WORKSPACE, INSTRUCTIONS
    _AGENT_ID = (agent_id or "buyer-a").strip() or "buyer-a"
    _DISPLAY = "采购商B" if _AGENT_ID == "buyer-b" else "采购商A"
    _WORKSPACE = Path(__file__).resolve().parents[1] / "workspaces" / f"{_AGENT_ID}-wit"
    INSTRUCTIONS = _render_instructions(_DISPLAY)
    get_buyer_tools().refresh_agent()


def _shortages_from_inventory_low() -> list[dict[str, Any]]:
    inv = bs.list_inventory()
    return [
        {
            "material_code": i["code"],
            "name": i["name"],
            "unit": i["unit"],
            "short_vs_safety": round(float(i["safety_stock"]) - float(i["available"]), 2),
            "preferred_supplier": i["preferred_supplier"],
            "need": max(float(i["safety_stock"]) - float(i["available"]), 1),
        }
        for i in inv
        if i.get("low")
    ]


def _build_capabilities(run_rfq: RfqFn | None) -> list[Any]:
    tools = get_buyer_tools()

    @capability(
        id="discover.suppliers",
        description=(
            "带着【全部】采购需求向梧桐ADP发现可能覆盖的供应商（先匹配，后询价，再决定拆单/竞价）。"
            "传 product_name；多物料务必传 lines_json="
            '[{"sku":"RM-CASTER-300","name":"重型脚轮","qty":500},{"sku":"RM-FABRIC-PRO","name":"高档面料","qty":500}]；'
            "query 用自然语言整句提问，例如「谁能提供500脚轮和500面料」。"
            "只开一案一套短名单；禁止未询价就因「一家盖不全」拆成两案。"
        ),
    )
    async def discover_suppliers_cap(
        query: str = "",
        product_name: str = "",
        quantity: int = 500,
        limit: int = 5,
        refresh: bool = False,
        lines_json: str = "",
    ) -> dict[str, Any]:
        pname = (product_name or "").strip()
        lines: list[Any] = []
        raw_lines = (lines_json or "").strip()
        if raw_lines:
            try:
                parsed = json.loads(raw_lines)
                if isinstance(parsed, list):
                    lines = parsed
            except json.JSONDecodeError:
                lines = []
        if not pname:
            cid0 = _active_case_id()
            brief = ((pc.get_case(cid0) or {}).get("brief") or {}) if cid0 else {}
            pname = str(brief.get("product_name") or "").strip()
            if not lines and isinstance(brief.get("lines"), list):
                lines = list(brief.get("lines") or [])
        if not pname and lines:
            pname = " + ".join(
                f"{(x or {}).get('name') or (x or {}).get('sku')}×{(x or {}).get('qty') or 1}"
                for x in lines
                if isinstance(x, dict)
            )
        if not pname:
            return {
                "ok": False,
                "error": {
                    "code": "PRODUCT_REQUIRED",
                    "message": "请传入 product_name 或 lines_json（组合需求），禁止默认成重型脚轮",
                },
            }
        q = (query or "").strip()
        if not q and lines and len(lines) >= 2:
            names = "和".join(
                str((x or {}).get("name") or (x or {}).get("sku") or "")
                for x in lines
                if isinstance(x, dict)
            )
            q = f"我需要购买{names}，哪家供应商符合我的需求？"
        out = await tools.discover_suppliers_tool(
            {
                "case_id": _active_case_id(),
                "query": q or f"供应 {pname}",
                "product_name": pname,
                "quantity": quantity,
                "limit": limit,
                "refresh": refresh,
                "lines": lines,
            }
        )
        if out.get("case_id"):
            _set_active_case(out["case_id"], product_name=pname)
        return out

    @capability(
        id="rfq.send_batch",
        description="对用户已确认短名单并行询价(1-5家)。selected 为 candidate_id 逗号分隔或JSON列表；等齐后拼接货+运报价。",
    )
    async def rfq_send_batch_cap(selected: str = "", case_id: str = "") -> dict[str, Any]:
        sel: list[Any]
        s = (selected or "").strip()
        if s.startswith("["):
            try:
                sel = json.loads(s)
            except json.JSONDecodeError:
                sel = [x.strip() for x in s.split(",") if x.strip()]
        else:
            sel = [x.strip() for x in s.split(",") if x.strip()]
        if not sel:
            return {"ok": False, "error": {"code": "VALIDATION", "message": "selected 不能为空（1-5个candidate_id）"}}
        out = await tools.rfq_send_batch({"case_id": case_id or _active_case_id(), "selected": sel[:5]})
        if out.get("case_id"):
            _set_active_case(out["case_id"])
        return out

    @capability(
        id="partner.dialog",
        description="与已筛选供应商单轮AIP对话。intent=negotiate|clarify|requote|initial_quote；议价用negotiate+goal_text。",
    )
    async def partner_dialog_cap(
        partner: str = "",
        intent: str = "negotiate",
        goal_text: str = "保质保交期前提下优化总价",
        message: str = "",
    ) -> dict[str, Any]:
        return await tools.partner_dialog(
            {
                "case_id": _active_case_id(),
                "partner": partner,
                "intent": intent,
                "goal_text": goal_text,
                "message": message,
            }
        )

    @capability(id="erp.query_inventory", description="查询原料库存与是否低于安全线。low_only=true仅看缺口。")
    def query_inventory(low_only: bool = False) -> dict[str, Any]:
        return tools.query_inventory(low_only=low_only)

    @capability(id="erp.query_orders", description="查询订单。kind=sales|purchase|all。")
    def query_orders(kind: str = "sales", limit: int = 20) -> dict[str, Any]:
        return tools.query_orders(kind=kind, limit=limit)

    @capability(id="erp.query_notifications", description="查询运营通知。")
    def query_notifications(unread_only: bool = False) -> dict[str, Any]:
        return tools.query_notifications(unread_only=unread_only)

    @capability(
        id="erp.rfq_by_shortage",
        description="按原料缺口快捷AIP补货询价（非正式采购发现流程）。",
    )
    async def rfq_by_shortage() -> dict[str, Any]:
        if run_rfq is None:
            return {"error": "询价通道未就绪"}
        payload = bs.latest_shortage_payload()
        if payload and payload.get("shortages"):
            shortages = bs.materials_for_rfq_from_shortage(payload)
        else:
            shortages = _shortages_from_inventory_low()
        if not shortages:
            return {"quote_count": 0, "results": [], "message": "当前没有原料缺口"}
        return await run_rfq(shortages)

    @capability(
        id="memory.inject",
        description="注入本案工作记忆。entries_json为[{key,value,tags}]；tags含 shared/关键 时写入跨对话共享库。共享数量必须在 value 中带 product/sku。",
    )
    def memory_inject(entries_json: str = "[]", case_id: str = "") -> dict[str, Any]:
        cid = case_id or _active_case_id()
        if not cid:
            return {"ok": False, "error": {"code": "NO_CASE", "message": "尚无案件"}}
        try:
            entries = json.loads(entries_json or "[]")
        except json.JSONDecodeError:
            return {"ok": False, "error": {"code": "VALIDATION", "message": "entries_json 非法"}}
        if not isinstance(entries, list):
            return {"ok": False, "error": {"code": "VALIDATION", "message": "entries 须为列表"}}
        brief = (pc.get_case(cid) or {}).get("brief") or {}
        product = str(brief.get("product_name") or "").strip()
        fixed: list[Any] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            row = dict(e)
            tags = {str(t) for t in (row.get("tags") or [])}
            if tags.intersection({"shared", "关键", "key", "key_fact", "constraint", "约束"}):
                val = row.get("value")
                if isinstance(val, (int, float, str)) and product:
                    # 裸数量 → 绑物料，防止「净采购500」串到别的 SKU
                    row["value"] = {"product": product, "qty": val, "note": str(row.get("key") or "shared")}
                elif isinstance(val, dict) and product and not (val.get("product") or val.get("sku")):
                    val = dict(val)
                    val["product"] = product
                    row["value"] = val
            fixed.append(row)
        return tools.memory.inject(cid, fixed)

    @capability(id="memory.extract", description="提取本案记忆。keys 逗号分隔；空则全量entries。")
    def memory_extract(keys: str = "", case_id: str = "") -> dict[str, Any]:
        cid = case_id or _active_case_id()
        if not cid:
            return {"ok": False, "error": {"code": "NO_CASE", "message": "尚无案件"}}
        key_list = [x.strip() for x in keys.split(",") if x.strip()]
        return tools.memory.extract(cid, keys=key_list or None)

    @capability(id="memory.record", description="记录关键事件节点。event名 + payload_json。")
    def memory_record(event: str = "", payload_json: str = "{}", case_id: str = "") -> dict[str, Any]:
        cid = case_id or _active_case_id()
        if not cid:
            return {"ok": False, "error": {"code": "NO_CASE", "message": "尚无案件"}}
        try:
            payload = json.loads(payload_json or "{}")
        except json.JSONDecodeError:
            payload = {"raw": payload_json}
        return tools.memory.record(cid, event=event or "note", payload=payload if isinstance(payload, dict) else {})

    @capability(id="calc.compare_table", description="把本案最新并行询价结果收成对比表（供展示）；并附带下一步可点选按钮。")
    def calc_compare_table(case_id: str = "") -> dict[str, Any]:
        return tools.calc_compare_table(case_id or _active_case_id())

    @capability(
        id="ui.offer_choices",
        description=(
            "AskUserQuestion 同款：歧义/多路径/不可逆前择路时出按钮。"
            "choices_json=[{id,label,message,primary?,hint?}]；推荐项第一并标（推荐）。"
            "禁止文字编号清单；禁止「要不要继续」假选择题；琐碎单步不要调。"
        ),
    )
    def ui_offer_choices(
        prompt: str = "",
        choices_json: str = "[]",
        case_id: str = "",
        allow_note: bool = True,
    ) -> dict[str, Any]:
        from commerce.choice_actions import normalize_offered_choices
        from commerce.hitl_policy import recommend_first, should_offer_choices

        cid = case_id or _active_case_id()
        widget = normalize_offered_choices(
            case_id=cid,
            prompt=prompt or "",
            choices_json=choices_json,
            allow_note=allow_note,
        )
        ch = recommend_first(list(widget.get("choices") or []))
        widget["choices"] = ch
        widget["prompt"] = prompt or ""
        if not should_offer_choices(branch_count=len(ch), ambiguous=len(ch) >= 2, irreversible=len(ch) >= 2):
            return {
                "ok": False,
                "skipped": True,
                "reason": "未达 AskUser 时机；请直接调业务工具或 flow.inspect_goal",
                "case_id": cid,
            }
        if cid:
            try:
                pc.update_case(cid, pending_choices=widget)
            except Exception:  # noqa: BLE001
                pass
        return {
            "ok": True,
            "case_id": cid,
            "choice_actions": widget,
            "ui_hint": widget.get("ui_hint"),
            "hitl": widget.get("hitl"),
            "note": "已生成可点选按钮；请用一两句话说明依据，不要再罗列同样的文字编号选项。",
        }

    @capability(
        id="flow.decide_order",
        description=(
            "选商生成订单草案。supplier_agent_id 可空=最低价；"
            "组合需求必须传 sku（如 RM-CASTER-300）指定本单物料，禁止用各行数量加总；"
            "人类若已改量（如改为500套），必须传 quantity=新数量，禁止仍按初询300下单；"
            "运费未定时会返回物流路径按钮。"
        ),
    )
    def flow_decide_order(
        supplier_agent_id: str = "",
        sku: str = "",
        quantity: int = 0,
    ) -> dict[str, Any]:
        cid = _active_case_id()
        if not cid:
            return {"error": "尚无采购案"}
        qty_arg = int(quantity) if quantity and int(quantity) > 0 else None
        case = fs.step_decide(
            cid,
            "order",
            supplier_agent_id=supplier_agent_id or None,
            sku=sku or None,
            quantity=qty_arg,
        )
        draft = (case.get("order_draft") or {}).get("payload") or {}
        ship = draft.get("shipping_cost")
        freight_missing = ship is None or bool(draft.get("shipping_unknown"))
        out: dict[str, Any] = {
            "case_id": case["case_id"],
            "state": case["state"],
            "selected": case.get("selected_supplier"),
            "sku": draft.get("sku"),
            "product_name": draft.get("product_name"),
            "quantity": draft.get("quantity"),
            "goods_total": draft.get("goods_total"),
            "shipping_cost": ship,
            "shipping_unknown": freight_missing,
        }
        if freight_missing:
            from commerce.choice_actions import post_freight_path_choices

            widget = post_freight_path_choices(
                case_id=cid,
                supplier_agent_id=str(case.get("selected_supplier") or supplier_agent_id or ""),
            )
            try:
                pc.update_case(cid, pending_choices=widget)
            except Exception:  # noqa: BLE001
                pass
            out["choice_actions"] = widget
            out["ui_hint"] = widget.get("ui_hint")
            out["presentation_hint"] = (
                "运费未定：必须用按钮展示「自己联系物流 / 请对方联系物流」等路径；"
                "禁止只催供应侧出运价，禁止把运费当 0。"
            )
        return out

    @capability(
        id="flow.inspect_goal",
        description=(
            "诊断当前采购目标缺口（blockers）。工具失败或不知下一步时先调；"
            "按 next_actions / repair_tool 行动，不要穷举猜测。"
        ),
    )
    def flow_inspect_goal(order_ticket_id: str = "") -> dict[str, Any]:
        from commerce import goal_runtime as gr
        from commerce import tickets as tk

        cid = _active_case_id()
        case = pc.get_case(cid) if cid else None
        order = None
        tid = (order_ticket_id or "").strip()
        if tid:
            order = tk.get_ticket(_AGENT_ID, tid)
        elif cid:
            for t in tk.list_tickets(_AGENT_ID, limit=20) or []:
                if t.get("kind") == "order" and (t.get("case_id") == cid or True):
                    order = t
                    if (t.get("state") or {}).get("order_effective"):
                        break
        return gr.inspect_case_goal(case, agent_id=_AGENT_ID, order_ticket=order)

    @capability(
        id="flow.backfill_specs",
        description=(
            "承运缺体积/重量时调用：从物料主数据或向供应 clarify 补规格并写回订单；"
            "成功后重试 flow.request_shipping / flow.place_logistics_order。"
        ),
    )
    async def flow_backfill_specs(
        order_ticket_id: str = "",
        supplier_agent_id: str = "",
        ask_supplier: bool = True,
    ) -> dict[str, Any]:
        from commerce import goal_runtime as gr
        from commerce import tickets as tk

        cid = _active_case_id()
        tid = (order_ticket_id or "").strip() or None
        if not tid:
            for t in tk.list_tickets(_AGENT_ID, limit=20) or []:
                if t.get("kind") != "order":
                    continue
                if (t.get("state") or {}).get("order_effective") and not (t.get("state") or {}).get("cancelled"):
                    tid = str(t.get("id") or "")
                    break
        return await gr.backfill_specs(
            _AGENT_ID,
            case_id=cid,
            order_ticket_id=tid,
            supplier_agent_id=(supplier_agent_id or None),
            ask_supplier=bool(ask_supplier),
        )

    @capability(
        id="flow.request_shipping",
        description=(
            "向物流拿结构化运费报价。缺 volume/weight 时返回 blockers（勿瞎用默认吨位）；"
            "先 flow.backfill_specs。正式下承运工单用 flow.place_logistics_order。"
        ),
    )
    async def flow_request_shipping(weight_kg: float = 0.0, postal_code: str = "") -> dict[str, Any]:
        from commerce import goal_runtime as gr

        cid = _active_case_id()
        if not cid:
            return gr.with_runtime_meta(
                {"error": "尚无采购案"},
                goal="询运",
                blockers=[gr.blocker(code="NO_CASE", message="尚无采购案", holder="buyer", repair_tool="discover.suppliers")],
            )
        case0 = pc.get_case(cid) or {}
        mass = fs._shipping_mass_from_case(case0, fallback_kg=200.0)
        bl = gr.shipping_blockers_from_mass(
            {
                "volume_m3": mass.get("volume_m3"),
                # 无真实推导且调用方未给重量时，不把默认 200kg 当已齐
                "weight_kg": mass.get("weight_kg") if mass.get("derived") or (weight_kg and float(weight_kg) > 0) else None,
            }
        )
        if bl:
            return gr.with_runtime_meta(
                {"case_id": cid, "error": "shipping_blocked", "mass": mass},
                goal="获得物流报价",
                blockers=bl,
            )
        dest = ""
        try:
            from commerce.merchant import buyer_destination

            dest = str((buyer_destination(_AGENT_ID) or {}).get("postal_code") or "")
        except Exception:  # noqa: BLE001
            dest = ""
        w_arg = float(weight_kg) if weight_kg and float(weight_kg) > 0 else float(mass.get("weight_kg") or 200.0)
        case = await fs.step_shipping(
            cid,
            weight_kg=w_arg,
            postal_code=(postal_code or dest or "071000"),
        )
        ship = ((case.get("shipping_quote") or {}).get("payload") or {})
        draft = ((case.get("order_draft") or {}).get("payload") or {})
        return gr.with_runtime_meta(
            {
                "case_id": case["case_id"],
                "state": case["state"],
                "shipping_cost": ship.get("shipping_cost"),
                "eta_days": ship.get("eta_days"),
                "weight_kg_used": ship.get("weight_kg") or draft.get("weight_kg"),
                "volume_m3_used": ship.get("volume_m3") or draft.get("volume_m3"),
                "sku": draft.get("sku"),
                "contract_ready": case.get("state") == "CONTRACT_PENDING",
                "note": "已获物流报价。人类确认下承运单后请调用 flow.place_logistics_order。",
                "next": "flow.place_logistics_order",
            },
            goal="物流单双方确认生效",
            next_actions=["flow.place_logistics_order", "ui.offer_choices"],
        )

    @capability(
        id="flow.place_logistics_order",
        description=(
            "人类已确认物流报价后：采购发起物流工单。缺规格时返回 blockers 并提示 backfill，禁止硬下。"
        ),
    )
    async def flow_place_logistics_order(order_ticket_id: str = "") -> dict[str, Any]:
        from commerce import goal_runtime as gr
        from commerce import logistics_tickets as lt
        from commerce import tickets as tk

        tid = (order_ticket_id or "").strip()
        if not tid:
            for t in tk.list_tickets(_AGENT_ID, limit=30) or []:
                if t.get("kind") != "order":
                    continue
                st = t.get("state") or {}
                if st.get("order_effective") and not st.get("cancelled"):
                    tid = str(t.get("id") or "")
                    break
        if not tid:
            return gr.with_runtime_meta(
                {"error": "未找到已生效的货物订单工单"},
                goal="下物流单",
                blockers=[
                    gr.blocker(
                        code="NO_ORDER_TICKET",
                        message="无已生效货物工单",
                        holder="buyer_human",
                        repair_tool="flow.decide_order",
                    )
                ],
            )
        order = tk.get_ticket(_AGENT_ID, tid)
        if not order:
            return {"error": f"工单不存在: {tid}", "ok": False}
        st = order.get("state") or {}
        if not st.get("order_effective"):
            return gr.with_runtime_meta(
                {"error": "货物订单尚未双方确认生效", "order_ticket_id": tid},
                goal="下物流单",
                blockers=[
                    gr.blocker(
                        code="ORDER_NOT_EFFECTIVE",
                        message="货物工单未生效",
                        holder="buyer_human",
                        repair_tool="ui.offer_choices",
                    )
                ],
            )
        if st.get("logistics_ticket_id"):
            return {
                "ok": True,
                "already": True,
                "logistics_ticket_id": st.get("logistics_ticket_id"),
                "note": "物流工单已存在，请在工单待办与物流双方确认。",
                "blockers": [],
            }
        summary = st.get("summary") if isinstance(st.get("summary"), dict) else {}
        mass = gr.collect_physical_specs(summary)
        cid = str(order.get("case_id") or _active_case_id() or "")
        if cid:
            case = pc.get_case(cid) or {}
            draft = ((case.get("order_draft") or {}).get("payload") or {})
            mass = gr.collect_physical_specs(mass, draft if isinstance(draft, dict) else {})
        bl = gr.shipping_blockers_from_mass(mass, order_ticket_id=tid)
        if bl:
            return gr.with_runtime_meta(
                {"error": "logistics_blocked", "order_ticket_id": tid, "mass": mass},
                goal="物流单双方确认生效",
                blockers=bl,
            )
        out = await lt.quote_and_spawn_from_order(_AGENT_ID, order_ticket=order)
        return gr.with_runtime_meta(
            {
                "ok": True,
                "order_ticket_id": tid,
                "logistics_ticket_id": out.get("ticket_id"),
                "quote": out.get("quote"),
                "note": "物流工单已生成（采购↔物流）。请双方在工单待办中人工确认后生效。",
            },
            goal="物流单双方确认生效",
            next_actions=["ui.offer_choices"],
        )

    @capability(
        id="flow.decide_auction",
        description="用户已选择组群竞价后调用：将本案切入 BIDDING。不要在用户未点选时调用。",
    )
    def flow_decide_auction() -> dict[str, Any]:
        cid = _active_case_id()
        if not cid:
            return {"error": "尚无采购案"}
        case = fs.step_decide(cid, "auction")
        return {"case_id": case["case_id"], "state": case["state"], "next": "请继续调用 flow.run_auction"}

    @capability(
        id="flow.run_auction",
        description="执行组群盲拍（失败回退1:1 AIP）；回执含出价与TCO方案。须已在 BIDDING（先 decide_auction）。",
    )
    async def flow_run_auction() -> dict[str, Any]:
        cid = _active_case_id()
        if not cid:
            return {"error": "尚无采购案"}
        case = await fs.step_auction(cid)
        summary = case.get("auction_summary") or {}
        schemes = summary.get("schemes") or []
        bids = case.get("auction_bids") or []
        # step_auction 已写入 pending_choices；此处再读一遍供对话回执挂 ui_widgets
        widget = case.get("pending_choices")
        if not widget:
            from commerce.choice_actions import post_auction_scheme_choices

            widget = post_auction_scheme_choices(case_id=cid, schemes=schemes, bids=bids)
            if widget:
                try:
                    pc.update_case(cid, pending_choices=widget)
                except Exception:  # noqa: BLE001
                    pass
        return {
            "case_id": case["case_id"],
            "state": case["state"],
            "auction_summary": summary,
            "bids": bids,
            "choice_actions": widget,
            "ui_hint": (widget or {}).get("ui_hint"),
            "note": "请用按钮让用户选方案；禁止自动成交。",
        }

    @capability(id="flow.hitl_decide", description="HITL：decision=approve|edit|reject|respond。")
    def flow_hitl_decide(decision: str = "approve", agent_ids: str = "", note: str = "") -> dict[str, Any]:
        cid = _active_case_id()
        if not cid:
            return {"error": "尚无采购案"}
        ids = [x.strip() for x in agent_ids.split(",") if x.strip()] or None
        case = fs.step_hitl_decide(cid, decision, agent_ids=ids, note=note)
        return {"case_id": case["case_id"], "state": case["state"], "voided": case.get("voided"), "hitl": case.get("hitl_pending")}

    @capability(id="flow.confirm_buyer", description="采购方确认合同。")
    def flow_confirm_buyer() -> dict[str, Any]:
        cid = _active_case_id()
        if not cid:
            return {"error": "尚无采购案"}
        case = fs.step_buyer_confirm(cid)
        return {"case_id": case["case_id"], "buyer_confirmed": case.get("buyer_confirmed")}

    @capability(id="flow.confirm_supplier", description="请求供应商确认合同。")
    async def flow_confirm_supplier() -> dict[str, Any]:
        cid = _active_case_id()
        if not cid:
            return {"error": "尚无采购案"}
        case = await fs.step_supplier_confirm(cid)
        return {"case_id": case["case_id"], "supplier_confirmed": case.get("supplier_confirmed")}

    @capability(id="flow.activate", description="双边确认后激活订单。")
    def flow_activate() -> dict[str, Any]:
        cid = _active_case_id()
        if not cid:
            return {"error": "尚无采购案"}
        case = fs.step_activate(cid)
        return {"case_id": case["case_id"], "state": case["state"]}

    @capability(
        id="flow.status",
        description=(
            "查看本窗绑定采购案状态、HITL，以及 state_focus（甲方/乙方/整案需求/本单行）。"
            "动手前先看清主体；不会自动改绑到其它历史案。"
        ),
    )
    def flow_status() -> dict[str, Any]:
        cid = _active_case_id()
        # 严禁：无活跃案时偷偷挂上「最新一案」（曾导致扶手对话串成脚轮案）
        if not cid:
            return {
                "message": "本窗尚无绑定采购案",
                "hint": "请先按用户全部需求调用 discover.suppliers（可多物料 lines）",
                "case_id": None,
                "state_focus": pc.describe_state_focus(None),
            }
        case = pc.get_case(cid)
        brief = (case or {}).get("brief") or {}
        focus = pc.describe_state_focus(case)
        return {
            "case_id": cid,
            "state": (case or {}).get("state"),
            "product_name": brief.get("product_name"),
            "quantity": brief.get("quantity"),
            "lines": brief.get("lines") or [],
            "hitl": (case or {}).get("hitl_pending"),
            "selected_supplier": (case or {}).get("selected_supplier"),
            "split_plan": (case or {}).get("split_plan"),
            "state_focus": focus,
            "reminder": (
                f"甲方={focus.get('party_a')}；乙方={focus.get('party_b')}；"
                f"整案需求={focus.get('demand_scope')}；本单行={focus.get('order_line') or '尚未拆单下单'}"
            ),
        }

    # 兼容旧名 → 新实现
    @capability(id="flow.discover", description="[兼容]同 discover.suppliers")
    async def flow_discover_compat(query: str = "") -> dict[str, Any]:
        return await discover_suppliers_cap(query=query)

    @capability(id="flow.confirm_shortlist_and_rfq", description="[兼容]确认短名单并询价；agent_ids 逗号分隔。")
    async def flow_confirm_compat(agent_ids: str = "") -> dict[str, Any]:
        ids = [x.strip() for x in agent_ids.split(",") if x.strip()] or [
            "supplier-a",
            "supplier-b",
            "supplier-c",
        ]
        return await rfq_send_batch_cap(selected=",".join(ids))

    @capability(id="erp.query_sales_orders", description="[兼容]同 erp.query_orders kind=sales")
    def query_sales_compat(limit: int = 20) -> dict[str, Any]:
        return tools.query_orders(kind="sales", limit=limit)

    return [
        discover_suppliers_cap,
        rfq_send_batch_cap,
        partner_dialog_cap,
        query_inventory,
        query_orders,
        query_notifications,
        rfq_by_shortage,
        memory_inject,
        memory_extract,
        memory_record,
        calc_compare_table,
        ui_offer_choices,
        flow_decide_order,
        flow_inspect_goal,
        flow_backfill_specs,
        flow_request_shipping,
        flow_place_logistics_order,
        flow_decide_auction,
        flow_run_auction,
        flow_hitl_decide,
        flow_confirm_buyer,
        flow_confirm_supplier,
        flow_activate,
        flow_status,
        flow_discover_compat,
        flow_confirm_compat,
        query_sales_compat,
    ]


def _amp_hooks() -> list[Any]:
    # Access 边界日志；完整六类 AMP 上报需平台入驻后挂 AcpsConfig + 证书身份
    return [AmpAccessLoggingHooks()]


def _obs_tool_name(obs: dict[str, Any]) -> str:
    tool = obs.get("tool")
    if isinstance(tool, dict):
        tool = tool.get("name") or tool.get("id")
    name = (
        obs.get("modelToolName")
        or obs.get("capabilityId")
        or obs.get("tool_name")
        or obs.get("name")
        or tool
        or ""
    )
    return str(name).replace(".", "_").replace("-", "_").lower()


def _as_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _obs_content(obs: dict[str, Any]) -> dict[str, Any] | None:
    return (
        _as_dict(obs.get("result"))
        or _as_dict(obs.get("content"))
        or _as_dict(obs.get("observation"))
        or _as_dict(obs.get("output"))
    )


def _extract_rfq_from_observations(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    for obs in reversed(observations or []):
        if not isinstance(obs, dict):
            continue
        name = _obs_tool_name(obs)
        content = _obs_content(obs)
        if content is None:
            continue
        if "rfq_by_shortage" in name or "erp_rfq" in name:
            return content
        if "quote_count" in content or "results" in content:
            return content
    return None


def _extract_ui_widgets(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从工具回执抽出前端可渲染的交互件（短名单 / 比价表 / 点选按钮）。"""
    widgets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obs in observations or []:
        if not isinstance(obs, dict):
            continue
        content = _obs_content(obs)
        if not content:
            continue
        hint = content.get("ui_hint") if isinstance(content.get("ui_hint"), dict) else {}
        form = hint.get("form")
        view = hint.get("view")
        if form == "shortlist_confirm" and content.get("candidates"):
            key = f"shortlist:{content.get('case_id')}:{len(content.get('candidates') or [])}"
            if key in seen:
                continue
            seen.add(key)
            widgets.append(
                {
                    "kind": "shortlist_confirm",
                    "case_id": content.get("case_id"),
                    "candidates": content.get("candidates"),
                    "ui_hint": hint,
                    "hitl": content.get("hitl"),
                    "source": content.get("source"),
                }
            )
        if view == "quote_compare_table":
            table = hint.get("table") or content.get("table")
            quotes = content.get("quotes")
            key = f"quotes:{content.get('case_id')}:{len(quotes or [])}:{bool(table)}"
            if key not in seen:
                seen.add(key)
                widgets.append(
                    {
                        "kind": "quote_compare_table",
                        "case_id": content.get("case_id"),
                        "quotes": quotes,
                        "table": table,
                        "summary": content.get("summary"),
                        "ui_hint": hint,
                        "hitl": content.get("hitl"),
                    }
                )
        # 点选按钮：独立 form，或挂在比价/议价回执上
        ca = content.get("choice_actions")
        choices = None
        prompt = None
        allow_note = True
        if isinstance(ca, dict) and ca.get("choices"):
            choices = ca.get("choices")
            prompt = ca.get("prompt")
            allow_note = bool(ca.get("allow_note", True))
        elif form == "choice_actions" and hint.get("choices"):
            choices = hint.get("choices")
            prompt = hint.get("title") or (content.get("hitl") or {}).get("prompt")
            allow_note = bool(hint.get("allow_note", True))
        if choices:
            key = f"choices:{content.get('case_id')}:{len(choices)}:{prompt}"
            if key not in seen:
                seen.add(key)
                widgets.append(
                    {
                        "kind": "choice_actions",
                        "case_id": content.get("case_id"),
                        "prompt": prompt or "请点选下一步（可填补充说明）",
                        "allow_note": allow_note,
                        "choices": choices,
                        "ui_hint": hint or {"form": "choice_actions"},
                        "hitl": content.get("hitl") or (ca or {}).get("hitl"),
                    }
                )
    return widgets


def _build_runtime(
    run_rfq: RfqFn | None,
    *,
    thread_id: str | None = None,
) -> tuple[Any, OpenAIChatProvider]:
    from commerce import chat_sessions as cs

    settings = llm_settings()
    provider = OpenAIChatProvider(
        model=settings["model"],
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        temperature=0.2,
    )
    tid = cs.ensure_thread(_AGENT_ID, thread_id)
    _set_active_thread(tid)
    _restore_case_for_thread(tid)
    # 每窗独立 Wit 工作区 → 窗口记忆不共享
    ws = _WORKSPACE / "threads" / tid
    ws.mkdir(parents=True, exist_ok=True)
    subject = None
    meta = cs.get_thread_meta(_AGENT_ID, tid)
    subject = meta.get("subject_product")
    if not subject and _active_case_id():
        subject = ((pc.get_case(_active_case_id() or "") or {}).get("brief") or {}).get("product_name")
    shared_block = cs.shared_facts_prompt_block(_AGENT_ID, subject_product=str(subject) if subject else None)
    case_now = pc.get_case(_active_case_id() or "") if _active_case_id() else None
    focus_now = pc.describe_state_focus(case_now) if case_now else None
    if focus_now:
        subject_line = (
            f"\n\n【本窗甲乙方与主体】\n"
            f"- 状态 {focus_now.get('state')}：{focus_now.get('focus')}\n"
            f"- 甲方 {focus_now.get('party_a')}；乙方 {focus_now.get('party_b')}\n"
            f"- 整案需求：{focus_now.get('demand_scope')}\n"
            f"- 本单行（拆单后才有）：{focus_now.get('order_line') or '尚未生成订单草案'}\n"
            "整案阶段围绕全部需求发现/询价；下单后每单只谈该行与该乙方，禁止把其它物料塞进该单。"
        )
    elif subject:
        subject_line = (
            f"\n\n【本窗采购主体】{subject}\n"
            "先按全部需求发现与询价；若多物料由不同供方覆盖则拆单；禁止偷换 SKU。"
        )
    else:
        subject_line = (
            "\n\n【本窗采购主体】尚未绑定。"
            "用户点名需求（可多种物料）后，discover 必须带齐全部需求，禁止默认「重型脚轮」。"
        )
    instructions = INSTRUCTIONS + subject_line + ("\n\n" + shared_block if shared_block else "")
    agent = WitAgent(
        id=f"{_AGENT_ID}:{tid}",
        display_name=_DISPLAY,
        instructions=instructions,
        model=provider,
        capabilities=_build_capabilities(run_rfq),
        amp_hooks=_amp_hooks(),
        description=f"采联{_DISPLAY}运营助手（Wit + DeepSeek）·窗 {tid}",
    )
    return WitRuntime(agent, workspace=ws), provider


def _finalize_from_run(
    *,
    reply: str,
    observations: list[dict[str, Any]],
    status: str | None = None,
    iterations: int | None = None,
) -> dict[str, Any]:
    reply = (reply or "").strip() or "（模型未返回文本）"
    rfq = _extract_rfq_from_observations(observations)
    widgets = _extract_ui_widgets(observations)
    meta: dict[str, Any] = {
        "intent": "rfq" if rfq and rfq.get("quote_count") else "wit_chat",
        "engine": "wit",
    }
    if status is not None:
        meta["status"] = status
    if iterations is not None:
        meta["iterations"] = iterations
    if rfq:
        meta["result"] = rfq
        meta["intent"] = "rfq" if int(rfq.get("quote_count") or 0) > 0 or "results" in rfq else "rfq_none"
    if widgets:
        meta["ui_widgets"] = widgets
        kinds = {w.get("kind") for w in widgets}
        if "shortlist_confirm" in kinds:
            meta["intent"] = "shortlist_hitl"
        elif "choice_actions" in kinds and meta["intent"] == "wit_chat":
            meta["intent"] = "choice_hitl"
        elif "quote_compare_table" in kinds and meta["intent"] == "wit_chat":
            meta["intent"] = "quote_compare"
    if _active_case_id():
        meta["case_id"] = _active_case_id()
        case = pc.get_case(_active_case_id() or "")
        if case:
            meta["case_state"] = case.get("state")
            meta["hitl_pending"] = case.get("hitl_pending")
    from commerce import chat_sessions as cs

    meta["thread_id"] = cs.active_thread_id(_AGENT_ID)
    bs.append_conversation("assistant", reply, meta, thread_id=meta.get("thread_id"))
    out: dict[str, Any] = {"reply": reply, "intent": meta["intent"], "engine": "wit", "thread_id": meta.get("thread_id")}
    if rfq:
        out["data"] = rfq
    if widgets:
        out["ui_widgets"] = widgets
    if meta.get("case_id"):
        out["case_id"] = meta["case_id"]
        out["case_state"] = meta.get("case_state")
        out["hitl_pending"] = meta.get("hitl_pending")
    return out


def _tool_status_label(name: str, *, done: bool = False) -> str:
    raw = (name or "").strip()
    n = raw.replace("-", "_").lower()
    labels = {
        "discover.suppliers": ("正在梧桐平台发现供应商…", "供应商发现完成，请勾选短名单"),
        "rfq.send_batch": ("正在并行向短名单询价（货款）…", "并行询价完成"),
        "partner.dialog": ("正在与供应商对话…", "供应商对话完成"),
        "erp.query_inventory": ("正在查询原料库存与安全线…", "库存查询完成"),
        "erp.query_orders": ("正在查询订单…", "订单查询完成"),
        "erp.query_sales_orders": ("正在查询销售订单…", "销售订单查询完成"),
        "erp.query_notifications": ("正在查询通知中心…", "通知查询完成"),
        "erp.rfq_by_shortage": ("正在按缺口向上游供应商询价…", "缺口询价完成"),
        "memory.inject": ("正在写入工作记忆…", "工作记忆已写入"),
        "memory.extract": ("正在读取工作记忆…", "工作记忆已提取"),
        "memory.record": ("正在记录关键事件…", "关键事件已记录"),
        "calc.compare_table": ("正在生成比价表…", "比价表已就绪"),
        "ui.offer_choices": ("正在生成可点选按钮…", "请点选下一步（可填补充）"),
        "flow.discover": ("正在梧桐平台发现符合条件的供应商智能体…", "供应商发现完成"),
        "flow.confirm_shortlist_and_rfq": ("正在确认短名单，并经 AIP 向供应商询价…", "短名单询价完成"),
        "flow.decide_order": ("正在按对比结果生成订单草案…", "订单草案已生成"),
        "flow.inspect_goal": ("正在诊断目标缺口…", "缺口诊断完成"),
        "flow.backfill_specs": ("正在补齐体积/重量规格…", "规格已写回订单"),
        "flow.request_shipping": ("正在向物流询运报价…", "物流报价已到"),
        "flow.place_logistics_order": ("正在生成物流工单…", "物流工单已生成，请双方确认"),
        "flow.decide_auction": ("正在切入组群竞价…", "已进入竞价态，准备开拍"),
        "flow.run_auction": ("正在组群盲拍并合入物流 TCO…", "组群竞价回执已到"),
        "flow.hitl_decide": ("正在登记人工决策…", "人工决策已登记"),
        "flow.confirm_buyer": ("正在登记采购方合同确认…", "采购方已确认"),
        "flow.confirm_supplier": ("正在经 AIP 请求供应商确认合同…", "供应商确认完成"),
        "flow.activate": ("正在激活订单…", "订单已激活"),
        "flow.status": ("正在读取采购案状态…", "状态已同步"),
    }
    if raw in labels:
        return labels[raw][1 if done else 0]
    if "discover" in n:
        return "供应商发现完成" if done else "正在梧桐平台查询符合条件的智能体…"
    if "send_batch" in n or ("rfq" in n and "shortage" not in n) or "shortlist" in n:
        return "询价完成" if done else "正在经 AIP 向上游供应商询价…"
    if "partner" in n or "dialog" in n or "negotiat" in n:
        return "伙伴对话完成" if done else "正在与供应商对话…"
    if "memory" in n:
        return "记忆操作完成" if done else "正在读写记忆…"
    if "compare" in n:
        return "比价表已就绪" if done else "正在生成比价表…"
    if "inventory" in n:
        return "库存查询完成" if done else "正在查询库存…"
    if "notif" in n:
        return "通知查询完成" if done else "正在查询通知…"
    if done:
        return f"工具已完成：{raw or '…'}"
    return f"正在调用工具 {raw or '…'}…"


def _tool_name_from_event(data: dict[str, Any], ev: Any) -> str:
    tool = data.get("tool_call") or data.get("tool") or {}
    if isinstance(tool, dict):
        return str(tool.get("name") or tool.get("id") or "")
    return str(data.get("tool_name") or getattr(ev, "name", "") or "")


async def stream_buyer_chat_wit(
    text: str,
    *,
    run_rfq: RfqFn | None = None,
    thread_id: str | None = None,
):
    """Yield SSE payload dicts: token / status / done / error."""
    from commerce import chat_sessions as cs
    from commerce.progress import drain_status_queue, make_queue_reporter, reset_progress, set_progress

    text = (text or "").strip()
    tid = cs.ensure_thread(_AGENT_ID, thread_id)
    cs.set_active_thread(_AGENT_ID, tid)
    bs.append_conversation("user", text, thread_id=tid)

    settings = llm_settings()
    if not settings["api_key"]:
        reply = "未配置 LLM_API_KEY，无法使用 Wit 对话。"
        bs.append_conversation("assistant", reply, {"intent": "llm_config_error"}, thread_id=tid)
        yield {"type": "error", "message": reply, "intent": "llm_config_error", "engine": "wit", "thread_id": tid}
        return

    runtime, provider = _build_runtime(run_rfq, thread_id=tid)
    tokens: list[str] = []
    observations: list[dict[str, Any]] = []
    final_reply = ""
    status = "ok"
    iterations = 0
    status_q: asyncio.Queue = asyncio.Queue(maxsize=200)
    progress_token = set_progress(make_queue_reporter(status_q))
    active_tool = ""

    async def _flush_progress():
        for item in await drain_status_queue(status_q):
            yield item

    try:
        yield {"type": "status", "text": "正在理解你的意图…", "phase": "think", "engine": "wit"}
        # 并行轮询进度队列，避免工具长时间阻塞时前端无状态
        stream = runtime.astream_events(text).__aiter__()
        next_ev = asyncio.create_task(stream.__anext__())
        while True:
            async for item in _flush_progress():
                yield item
            done, _ = await asyncio.wait({next_ev}, timeout=0.12)
            if not done:
                continue
            try:
                ev = next_ev.result()
            except StopAsyncIteration:
                break
            next_ev = asyncio.create_task(stream.__anext__())

            name = getattr(ev, "event", "") or ""
            data = dict(getattr(ev, "data", None) or {})
            if name in ("model.start", "llm.start", "step.start") and not tokens:
                yield {"type": "status", "text": "模型思考中…", "phase": "think"}
            elif name == "model.delta" and data.get("type") == "text":
                piece = str(data.get("text") or "")
                if piece:
                    if not tokens:
                        yield {"type": "status", "text": "正在组织回复…", "phase": "reply"}
                    tokens.append(piece)
                    yield {"type": "token", "text": piece}
            elif name == "tool.start":
                active_tool = _tool_name_from_event(data, ev)
                yield {
                    "type": "status",
                    "text": _tool_status_label(active_tool, done=False),
                    "phase": "tool",
                    "tool": active_tool,
                }
            elif name in ("tool.end", "tool.result"):
                tool_name = _tool_name_from_event(data, ev) or active_tool
                yield {
                    "type": "status",
                    "text": _tool_status_label(tool_name, done=True),
                    "phase": "tool_done",
                    "tool": tool_name,
                }
                active_tool = ""
            elif name == "step.end":
                for obs in data.get("observations") or []:
                    if isinstance(obs, dict):
                        observations.append(obs)
            elif name == "run.end":
                result = data.get("result") or {}
                if isinstance(result, dict):
                    parts = result.get("output_parts") or []
                    texts = []
                    for part in parts:
                        if isinstance(part, dict) and part.get("type") == "text":
                            texts.append(str(part.get("text") or ""))
                    final_reply = "".join(texts).strip()
                    for obs in result.get("observations") or []:
                        if isinstance(obs, dict):
                            observations.append(obs)
                    status = str(result.get("status") or status)
                    try:
                        iterations = int(result.get("iterations") or 0)
                    except (TypeError, ValueError):
                        iterations = 0

        if not next_ev.done():
            next_ev.cancel()
        async for item in _flush_progress():
            yield item
        reply = final_reply or "".join(tokens)
        out = _finalize_from_run(
            reply=reply,
            observations=observations,
            status=status,
            iterations=iterations,
        )
        yield {"type": "status", "text": "回复就绪", "phase": "done"}
        yield {"type": "done", **out}
    except Exception as exc:  # noqa: BLE001
        reply = f"Wit/LLM 调用失败：{exc}"
        bs.append_conversation("assistant", reply, {"intent": "wit_error", "error": str(exc)}, thread_id=tid)
        yield {"type": "error", "message": reply, "intent": "wit_error", "engine": "wit", "thread_id": tid}
    finally:
        reset_progress(progress_token)
        await provider.aclose()


async def handle_buyer_chat_wit(
    text: str,
    *,
    run_rfq: RfqFn | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"reply": "", "intent": "wit_chat", "engine": "wit"}
    async for ev in stream_buyer_chat_wit(text, run_rfq=run_rfq, thread_id=thread_id):
        if ev.get("type") == "done":
            out = {k: v for k, v in ev.items() if k != "type"}
        elif ev.get("type") == "error":
            out = {
                "reply": ev.get("message") or "调用失败",
                "intent": ev.get("intent") or "wit_error",
                "engine": "wit",
                "thread_id": ev.get("thread_id"),
            }
    return out
