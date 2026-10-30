# -*- coding: utf-8 -*-
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "commerce" / "choice_actions.py"
text = p.read_text(encoding="utf-8")
start = text.index("def post_quote_choices(")
end = text.index("def post_freight_path_choices(")
new = '''def post_quote_choices(
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
                label="按覆盖分两单采购",
                message=(
                    f"组合询价显示不同物料宜分供：{plan_txt}。"
                    "请按 split_plan 分别为各物料新建/切换采购案并 flow.decide_order 生成对应草案；"
                    "不要强行塞进同一订单。生成后用按钮让我确认。"
                ),
                primary=True,
                hint="按谁能供什么拆单，更贴合目录覆盖",
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
                        f"请以物料 {sku} 为主，调用 flow.decide_order supplier_agent_id={sid} "
                        "生成该物料订单草案；其它物料稍后处理。"
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
                    "请先 flow.decide_auction，再 flow.run_auction："
                    "对短名单发起组群盲拍，物流旁听合入到岸 TCO；"
                    "竞价结束后用按钮展示方案，由我点选最合适订货方案后再 flow.decide_order。"
                    "不要跳过确认、不要自动成交。"
                ),
                primary=True,
                hint=auction_hint
                or "需求多方可比时：密封再竞一轮，给出更经济合适的综合方案",
            )
        )
    if not suggest_split:
        choices.append(
            choice(
                id="order_lowest",
                label=f"直接选 {low} 下单草案",
                message=f"请调用 flow.decide_order，supplier_agent_id={low}，生成订单草案供我确认。",
                hint="接受当前报价，进入草案",
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
        prompt = "组合询价完成：建议分单采购。请点选（可先填补充说明）"
    elif offer_group_auction:
        prompt = "业务判断：较适合组群竞价。请点选路径（可先填补充说明）"
    else:
        prompt = "下一步请点选（可先填补充说明）"
    _ = coverage
    return wrap_choice_widget(
        case_id=case_id,
        prompt=prompt,
        choices=choices,
        gate="after_initial_quotes",
    )


'''
p.write_text(text[:start] + new + text[end:], encoding="utf-8")
print("OK")
