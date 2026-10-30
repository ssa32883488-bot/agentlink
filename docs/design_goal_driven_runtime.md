# 目标驱动运行时（对标 Claude Code 思考设计）

**日期**：2026-10-30

## 学到什么

Claude Code 并不靠提示词穷举「如果 A 就 B」：

1. **主循环**：有 tool_use 就执行，把 **tool_result 喂回模型** 再规划下一跳。
2. **原则短句**：如 “If an approach fails, diagnose why before switching tactics.”
3. **结构化失败**：结果可带错误/缺口，而不是散文结束。
4. **system-reminder**：系统把关键状态塞进回执，驱动续跑。

## 我们落地

| 组件 | 作用 |
|------|------|
| `commerce/goal_runtime.py` | blockers / next_actions / system_reminder 契约 |
| `commerce/hitl_policy.py` | AskUserQuestion 时机：歧义/≥2 路径/不可逆；禁止「要不要继续」 |
| `flow.inspect_goal` / `partner.inspect_goal` | 采购/供应/物流三侧诊断缺口与持有方 |
| `flow.backfill_specs` | 主数据或问供应 → 写回订单 → 再询运 |
| 询运/下物流 | 缺规格时 **返回 blockers**，禁止硬编默认吨位蒙混 |
| Wit（buyer / supplier-a\|b\|c / logistics） | 目标+原则；`ui.offer_choices` 经 `should_offer_choices` + `recommend_first` |

## AskUser 时机（六智能体共用）

**出按钮**：澄清模糊需求；路径分叉须人择一；不可逆确认前择路；`holder=buyer_human` 且有可执行动作。  
**不出**：单步直做；仅转述事实；用选项问「计划好不好/要不要继续」；缺口持有方是供应/系统（先 `repair_tool`）。  
推荐项必须第一并标「（推荐）」。

## 典型闭环

物流缺体积 → 回执 `MISSING_VOLUME` + `repair_tool=flow.backfill_specs`
→ 补规格写回 → `flow.request_shipping` / `place_logistics_order`。
缺规格 **不问人猜体积**，问持有方补数后再重试。
