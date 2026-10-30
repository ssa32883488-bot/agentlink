"""HITL / 选项时机策略 — 直接套皮 Claude Code AskUserQuestion + ExitPlanMode 的出现条件。

源参考（claude-code-python）：
- tools/ask_user_question_tool/prompt_definitions.py
- tools/exit_plan_mode_tool/prompt_definitions.py
- tools/todo_write_tool/prompt_document.py
- prompts/sections.py「If an approach fails, diagnose why before switching tactics.」

核心：不是每轮都弹按钮；只在「歧义 / 多路径 / 不可逆 / 计划待批」时问人。
"""
from __future__ import annotations

from typing import Any

# —— 与 AskUserQuestion 对齐的触发条件（翻译为采购域）——
ASK_WHEN = (
    "需要澄清模糊需求（物料/数量/起讫地不清）",
    "实现路径有分叉，须人择一（议价 / 拆单 / 竞价 / 直接下单）",
    "即将做不可逆或双边确认动作（下单草案、物流下单）前的路径确认",
    "工具 blockers.holder=buyer_human 且存在 ≥2 条可执行 next_actions",
)

ASK_NOT_WHEN = (
    "单一步骤可直接用工具完成（查库存、查价目、读工单）",
    "仅转述工具事实、无路径分叉",
    "用选项问「计划好不好 / 要不要继续」——那是 approval gate，不是澄清题",
    "信息已够却反复弹同一组按钮骚扰用户",
)


def should_offer_choices(
    *,
    gate: str | None = None,
    blockers: list[dict[str, Any]] | None = None,
    branch_count: int = 0,
    irreversible: bool = False,
    ambiguous: bool = False,
    already_offered_same: bool = False,
) -> bool:
    """是否应调用 ui.offer_choices / 挂 choice_actions。

    Claude Code 规则映射：
    - clarify ambiguity / preferences / direction → AskUserQuestion → True
    - 「Is my plan ready?」类 → False（应用 ExitPlanMode/确认工单，不是选择题）
    - 单步直做 → False
    """
    if already_offered_same:
        return False
    gate = (gate or "").strip().lower()
    # 审批类 gate：出确认工单按钮可以，但不要伪装成「计划好不好」的澄清题
    if gate in {"confirm_order", "confirm_logistics", "approve_plan"}:
        return irreversible or branch_count >= 2
    if ambiguous:
        return True
    if irreversible and branch_count >= 2:
        return True
    if branch_count >= 2:
        return True
    bl = blockers or []
    human_held = [b for b in bl if str(b.get("holder") or "") in {"buyer_human", "human", "user"}]
    if human_held and branch_count >= 1:
        return True
    # 缺口持有方是供应/系统：先工具补数，不问人「你觉得体积是多少」
    if bl and not human_held:
        return False
    return False


def recommend_first(choices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """AskUserQuestion：推荐项放第一并标注 (Recommended) / （推荐）。"""
    if not choices:
        return choices
    out = [dict(c) for c in choices]
    primary = next((i for i, c in enumerate(out) if c.get("primary")), 0)
    if primary != 0:
        out.insert(0, out.pop(primary))
    label = str(out[0].get("label") or "")
    if "推荐" not in label and "Recommended" not in label:
        out[0]["label"] = f"{label}（推荐）" if label else "推荐方案"
    out[0]["primary"] = True
    for c in out[1:]:
        c["primary"] = False
    return out


def choices_from_blockers(
    blockers: list[dict[str, Any]],
    *,
    case_id: str | None = None,
    allow_skip: bool = True,
) -> dict[str, Any] | None:
    """把 blockers 转成可点选按钮；仅当 should_offer_choices 为真时返回 widget。"""
    from commerce.choice_actions import choice, wrap_choice_widget

    bl = [b for b in (blockers or []) if isinstance(b, dict)]
    if not bl:
        return None
    human = [b for b in bl if str(b.get("holder") or "") in {"buyer_human", "human", "user"}]
    # 非人类持有：返回 None，逼模型走 repair_tool
    if not human and all(b.get("repair_tool") for b in bl):
        return None
    choices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for b in bl:
        tool = str(b.get("repair_tool") or "").strip()
        code = str(b.get("code") or "act")
        if tool and tool not in seen:
            seen.add(tool)
            msg = (
                f"缺口 {code}：{b.get('message')}。"
                f"请调用 {tool}"
                + (f"（{b.get('repair_hint')}）" if b.get("repair_hint") else "")
            )
            choices.append(
                choice(
                    id=f"repair_{code.lower()}",
                    label=str(b.get("repair_hint") or tool)[:24],
                    message=msg,
                    hint=str(b.get("holder") or ""),
                )
            )
    if allow_skip:
        choices.append(
            choice(
                id="defer",
                label="稍后再办",
                message="本轮先不处理该缺口，等待我下一步指示。",
            )
        )
    if not should_offer_choices(
        blockers=bl,
        branch_count=len(choices),
        irreversible=any(c.get("id", "").startswith("repair_") for c in choices),
    ):
        # 仍给出 widget 当人类持有；否则 None
        if not human:
            return None
    choices = recommend_first(choices)
    return wrap_choice_widget(
        case_id=case_id,
        prompt="",  # 不啰嗦；按钮自解释（对齐删掉「不要只打字」）
        choices=choices,
        gate="blocker_repair",
    )


# TodoWrite 风格：何时拆任务（给 Wit 提示词引用，不作硬编码状态机）
TODO_WHEN = (
    "≥3 个独立步骤（发现→询价→议价→下单→物流）",
    "非平凡组合需求 / 拆单 / 竞价",
    "用户一次性交代多件事",
)
TODO_NOT_WHEN = (
    "单步查询（看库存、看工单）",
    "<3 个琐碎步骤",
    "纯闲聊",
)
