"""Brutal local unit: AskUser timing + recommend_first + blockers→choices + goal recover shape."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commerce.goal_runtime import blocker, with_runtime_meta  # noqa: E402
from commerce.hitl_policy import (  # noqa: E402
    ASK_NOT_WHEN,
    ASK_WHEN,
    choices_from_blockers,
    recommend_first,
    should_offer_choices,
)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_should_offer() -> None:
    # 单路径 / 无歧义 → 不出
    assert_true(not should_offer_choices(branch_count=0), "0 branch")
    assert_true(not should_offer_choices(branch_count=1), "1 branch alone")
    # ≥2 路径 → 出
    assert_true(should_offer_choices(branch_count=2), "2 branches")
    assert_true(should_offer_choices(ambiguous=True), "ambiguous")
    assert_true(should_offer_choices(irreversible=True, branch_count=2), "irreversible fork")
    # 「计划好不好」式 approval 且无分叉 → 不出澄清题
    assert_true(
        not should_offer_choices(gate="approve_plan", branch_count=1, irreversible=False),
        "approve_plan no fork",
    )
    # 人类持有 blocker + 至少一动作 → 出
    bl = [blocker(code="X", message="m", holder="buyer_human", repair_tool="ui.offer_choices")]
    assert_true(should_offer_choices(blockers=bl, branch_count=1), "human held")
    # 供应持有缺口：不问人猜体积
    bl2 = [blocker(code="MISSING_VOLUME", message="缺体积", holder="supplier", repair_tool="flow.backfill_specs")]
    assert_true(not should_offer_choices(blockers=bl2, branch_count=0), "supplier held no ask")
    assert_true(not should_offer_choices(already_offered_same=True, branch_count=3), "dedupe")


def test_recommend_first() -> None:
    ch = [
        {"id": "a", "label": "议价", "primary": False},
        {"id": "b", "label": "直接下单", "primary": True},
        {"id": "c", "label": "拆单", "primary": False},
    ]
    out = recommend_first(ch)
    assert_true(out[0]["id"] == "b", f"primary first got {out[0]}")
    assert_true("推荐" in out[0]["label"], out[0]["label"])
    assert_true(out[0]["primary"] is True and out[1]["primary"] is False, "flags")


def test_choices_from_blockers() -> None:
    # 非人类 + 有 repair → None（逼走工具）
    bl = [
        blocker(
            code="MISSING_VOLUME",
            message="缺体积",
            holder="buyer",
            repair_tool="flow.backfill_specs",
            repair_hint="补规格",
        )
    ]
    # holder=buyer 不算 buyer_human — choices_from_blockers 对非 human 且有 repair 返回 None
    w = choices_from_blockers(bl)
    assert_true(w is None, f"expected None for non-human repair, got {w}")

    bl_h = [
        blocker(
            code="MULTI_ORDER",
            message="多笔待确认",
            holder="buyer_human",
            repair_tool="ui.offer_choices",
            repair_hint="点选工单",
        )
    ]
    w2 = choices_from_blockers(bl_h, case_id="c1")
    assert_true(w2 is not None and w2.get("choices"), w2)
    assert_true("推荐" in (w2["choices"][0].get("label") or ""), w2["choices"][0])


def test_goal_recover_shape() -> None:
    """物流缺规格 → blockers + repair_tool，形状与 Claude 失败回执对齐。"""
    out = with_runtime_meta(
        {"error": {"code": "MISSING_VOLUME"}},
        goal="完成物流下单",
        blockers=[
            blocker(
                code="MISSING_VOLUME",
                message="缺体积无法询运",
                holder="buyer",
                fields=["volume_m3"],
                repair_tool="flow.backfill_specs",
                repair_hint="向供应补规格后重试",
            )
        ],
        next_actions=["flow.backfill_specs", "flow.request_shipping"],
    )
    assert_true(out.get("blockers") and out["blockers"][0]["repair_tool"] == "flow.backfill_specs", out)
    assert_true("system_reminder" in out or out.get("next_actions"), out)
    # 缺规格时不应出「你猜体积」类 AskUser
    assert_true(
        not should_offer_choices(blockers=out["blockers"], branch_count=0),
        "must not AskUser for supplier/buyer data gap",
    )


def test_principles_documented() -> None:
    assert_true(len(ASK_WHEN) >= 3 and len(ASK_NOT_WHEN) >= 3, "policy text")


def main() -> None:
    test_should_offer()
    test_recommend_first()
    test_choices_from_blockers()
    test_goal_recover_shape()
    test_principles_documented()
    # import-parse logistics/buyer/supplier wit modules lightly
    import ast

    for rel in (
        "commerce/hitl_policy.py",
        "commerce/goal_runtime.py",
        "commerce/chat_logistics_wit.py",
        "commerce/chat_supplier_wit.py",
        "commerce/chat_buyer_wit.py",
        "agents/logistics/main.py",
    ):
        ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    print(json.dumps({"ok": True, "suite": "hitl_askuser_policy"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
