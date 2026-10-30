"""人机选择：结构化按钮选项（禁止只拿编号清单逼用户打字）。"""
from __future__ import annotations

from typing import Any


def choice(
    *,
    id: str,
    label: str,
    message: str,
    primary: bool = False,
    hint: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "message": message,
        "primary": primary,
        "hint": hint,
    }


def wrap_choice_widget(
    *,
    case_id: str | None,
    prompt: str,
    choices: list[dict[str, Any]],
    allow_note: bool = True,
    gate: str = "user_choice",
) -> dict[str, Any]:
    return {
        "kind": "choice_actions",
        "case_id": case_id,
        "prompt": prompt,
        "allow_note": allow_note,
        "choices": choices,
        "hitl": {"gate": gate, "prompt": prompt},
        "ui_hint": {
            "form": "choice_actions",
            "title": prompt,
            "allow_note": allow_note,
            "choices": choices,
        },
    }


def post_quote_choices(
    *,
    case_id: str | None,
    lowest_agent_id: str | None = None,
    supplier_ids: list[str] | None = None,
    offer_group_auction: bool = False,
    auction_hint: str | None = None,
    split_plan: list[dict[str, Any]] | None = None,
    coverage: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """询价对比后的路径选择：分单建议 / 议价 /（适合时）组群竞价 / 选商下单。"""
    ids = [s for s in (supplier_ids or []) if s]
    low = lowest_agent_id or (ids[0] if ids else "supplier-a")
    talk_targets = [s for s in ids if s != low][:2] or ["supplier-c"]
    talk_ids = ",".join([low, *talk_targets][:2])
    plan = [x for x in (split_plan or []) if isinstance(x, dict) and x.get("supplier_agent_id")]
    suggest_split = len(plan) >= 2 and len({str(x.get("supplier_agent_id")) for x in plan}) >= 2
    choices: list[dict[str, Any]] = []
    if suggest_split:
        bits = [f"{x.get('sku')}→{x.get('supplier_agent_id')}" for x in plan]
        plan_txt = "；".join(bits)
        choices.append(
            choice(
                id="split_orders",
                label="按覆盖拆需求·分别下单",
                message=(
                    f"覆盖面显示没有任何一家能单独吃下全部需求，宜拆单：{plan_txt}。"
                    "请按 split_plan 对每个「供方+SKU」分别 flow.decide_order(supplier_agent_id, sku=该行SKU)；"
                    "每单甲方仍是采购、乙方是该供方、主体只是该行物料；"
                    "禁止把其它行品名写进该单标题/草案，禁止把多行 qty 加总。生成后用按钮让我逐单确认。"
                ),
                primary=True,
                hint="先整案询价看清谁盖哪一行，再拆——不是一单硬塞多家目录",
            )
        )
        for x in plan[:3]:
            sid = str(x.get("supplier_agent_id"))
            sku = str(x.get("sku") or "物料")
            choices.append(
                choice(
                    id=f"order_{sid}_{sku}",
                    label=f"先下 {sku}（{sid}）",
                    message=(
                        f"请调用 flow.decide_order，supplier_agent_id={sid}，sku={sku}，"
                        "只生成该物料订单草案（数量用该行 qty，禁止把其它物料数量加总）；"
                        "其它物料稍后处理。"
                    ),
                    hint=f"单价/行价以 {sku} 询价回执为准",
                )
            )
    choices.append(
        choice(
            id="negotiate_top",
            label="去议价（谈满减/补贴）",
            message=(
                f"请对 {talk_ids} 分别用 partner.dialog intent=negotiate 议价；"
                "目标谈满减门槛与（若有）跨省补贴，不要死压单价，也不要问我预算；"
                "议价后给出多方案按钮供我点选。"
            ),
            primary=not suggest_split and not offer_group_auction,
            hint="适合还想压综合成本或确认活动条件",
        )
    )
    if offer_group_auction and not suggest_split:
        choices.append(
            choice(
                id="group_auction",
                label="发起组群竞价（多方协商 + TCO）",
                message=(
                    "当前是同一需求、多家供应均可比：请先 flow.decide_auction，再 flow.run_auction；"
                    "短名单组群盲拍，物流旁听合入到岸 TCO；竞价后用按钮展示方案，"
                    "我点选后再 flow.decide_order。甲方=采购，乙方=竞价组内供方；不要自动成交。"
                ),
                primary=True,
                hint=auction_hint
                or "多家都能供同一物料时：组群压TCO；组合未覆盖齐应先拆单而不是开拍",
            )
        )
    if not suggest_split:
        choices.append(
            choice(
                id="order_lowest",
                label=f"直接选 {low} 下单草案",
                message=(
                    f"请调用 flow.decide_order，supplier_agent_id={low}；"
                    "若我已改量（例如改为500），必须传 quantity=最终数量并按议价活动结算，"
                    "禁止仍按初询数量下单；生成订单草案供我确认。"
                ),
                hint="接受当前报价，进入草案；改量须带 quantity",
            )
        )
    choices.append(
        choice(
            id="clarify_subsidy",
            label="先问清山西补贴再比",
            message=(
                "请对 supplier-c 用 partner.dialog intent=clarify，"
                "问清跨省运费补贴审核进度、能否确定抵扣金额与交期；暂不选商下单。"
            ),
            hint="补贴不确定时先澄清",
        )
    )
    if suggest_split:
        prompt = "整案询价已看清覆盖：需拆需求、分别对乙方下单。请点选（可先填补充说明）"
    elif offer_group_auction:
        prompt = "同一需求多方可比：可组群竞价求更优方案。请点选（可先填补充说明）"
    else:
        prompt = "下一步请点选（可先填补充说明）"
    _ = coverage
    return wrap_choice_widget(
        case_id=case_id,
        prompt=prompt,
        choices=choices,
        gate="after_initial_quotes",
    )


def post_order_effective_logistics_choices(
    *,
    case_id: str,
    order_ticket_id: str,
    origin_city: str = "沧州",
    dest_city: str = "保定",
    volume_m3: Any = None,
) -> dict[str, Any]:
    """采购订单生效后：引导人类去与物流对话询价/下单（不自动拉单）。"""
    vol = volume_m3 if volume_m3 is not None else "按订单规格"
    utter = (
        f"我打算下一个物流单，总体积为{vol}，起点{origin_city}到{dest_city}，请给我报价"
    )
    choices = [
        choice(
            id="dialog_logistics_quote",
            label="去和物流询价下单",
            message=(
                f"采购订单 {order_ticket_id} 已生效。请引导我用对话联系物流："
                f"先说「{utter}」；拿到报价后人类确认再 flow.place_logistics_order；"
                "禁止自动替我下物流单，禁止再让供应商联系物流。"
            ),
            primary=True,
            hint="对话驱动 · 采购↔物流",
        ),
        choice(
            id="defer_logistics",
            label="稍后再联系物流",
            message="本单物流稍后再办；先不要 flow.place_logistics_order。",
        ),
    ]
    return wrap_choice_widget(
        case_id=case_id,
        prompt="货物订单已生效。请点选是否立即与物流智能体沟通承运下单：",
        choices=choices,
        gate="after_order_effective",
    )


def post_freight_path_choices(
    *,
    case_id: str | None,
    supplier_agent_id: str | None = None,
) -> dict[str, Any]:
    """运费未定时的路径：采购自行联系物流对话；不再请供应代询。"""
    _ = supplier_agent_id
    choices = [
        choice(
            id="buyer_contact_logistics",
            label="与物流对话询运/下单",
            message=(
                f"我方自行联系物流（本案 {case_id or ''}）："
                "先用对话说明体积与起讫地询价；人类确认报价后调用 flow.place_logistics_order；"
                "也可先 flow.request_shipping 拿结构化运费。禁止催供应商出运费。"
            ),
            primary=True,
            hint="采购侧直接找物流 Agent",
        ),
        choice(
            id="defer_contract",
            label="暂缓，先不生成合同",
            message="运费路径未定，暂缓生成合同；保留订单草案，等我下一步指示。",
        ),
        choice(
            id="reject_draft",
            label="拒绝当前草案",
            message="请 flow.hitl_decide decision=reject，作废当前订单草案；不要继续催运费。",
        ),
    ]
    return wrap_choice_widget(
        case_id=case_id,
        prompt="运费未定：请点选是否与物流智能体对话询运/下单（可填补充说明）",
        choices=choices,
        gate="request_shipping",
    )


def post_auction_scheme_choices(
    *,
    case_id: str | None,
    schemes: list[dict[str, Any]] | None = None,
    bids: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """组群竞价开标后的选商按钮：优先 TCO 方案，否则回退出价。"""
    pick: list[dict[str, Any]] = []
    for sch in (schemes or [])[:5]:
        if not isinstance(sch, dict):
            continue
        sid = str(sch.get("supplier_agent_id") or sch.get("agent_id") or "")
        if not sid:
            continue
        tco = sch.get("tco") or sch.get("grand_total") or sch.get("total")
        pick.append(
            choice(
                id=f"order_{sid}",
                label=f"选 {sid} 下单（TCO {tco}）",
                message=(
                    f"请 flow.decide_order，supplier_agent_id={sid}，"
                    "按组群竞价结果生成订单草案。"
                ),
                primary=len(pick) == 0,
                hint="以组群 TCO/出价为准",
            )
        )
    if not pick:
        for b in bids or []:
            if not isinstance(b, dict) or b.get("unit_price") is None:
                continue
            sid = str(b.get("supplier_agent_id") or "")
            if not sid:
                continue
            pick.append(
                choice(
                    id=f"order_{sid}",
                    label=f"选 {sid}（出价 {b.get('unit_price')}）",
                    message=f"请 flow.decide_order，supplier_agent_id={sid}。",
                    primary=len(pick) == 0,
                )
            )
    if not pick:
        return None
    return wrap_choice_widget(
        case_id=case_id,
        prompt="组群竞价已完成，请点选订货方案",
        choices=pick,
        gate="bid_review",
    )


def normalize_offered_choices(
    *,
    case_id: str | None,
    prompt: str,
    choices_json: list[dict[str, Any]] | str,
    allow_note: bool = True,
) -> dict[str, Any]:
    """供 ui.offer_choices 工具：把模型给的选项收成标准 widget。"""
    import json

    raw = choices_json
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    choices: list[dict[str, Any]] = []
    for i, row in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("title") or f"选项{i+1}").strip()
        msg = str(row.get("message") or row.get("action") or label).strip()
        if not label:
            continue
        choices.append(
            choice(
                id=str(row.get("id") or f"opt-{i+1}"),
                label=label,
                message=msg,
                primary=bool(row.get("primary")),
                hint=str(row.get("hint") or "") or None,
            )
        )
    if not choices:
        choices = [
            choice(
                id="continue",
                label="继续",
                message="请根据当前上下文继续推进，并再次给出可点选按钮。",
                primary=True,
            )
        ]
    from commerce.hitl_policy import recommend_first

    return wrap_choice_widget(
        case_id=case_id,
        prompt=prompt or "",
        choices=recommend_first(choices),
        allow_note=allow_note,
    )
