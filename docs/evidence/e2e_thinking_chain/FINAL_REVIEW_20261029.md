# E2E 复盘 · 2026-10-29

| 场景 | 结果 | 证据 |
|------|------|------|
| S1 组合拆单（脚轮300 + 面料） | PASS | `fast_20261029_183158` |
| S2 组群竞价（CASTER-200 · A/C） | PASS | `s2fix_20261029_185546` |

## S1 组合拆单
- 覆盖：`RM-CASTER-300→supplier-a` / `RM-FABRIC-PRO→supplier-b`
- 双工单：`…-M-CASTER-300` + `…-M-FABRIC-PRO`，标题无产品摘要（无串货）
- 物流：沧州→保定（A）+ 邢台→保定（B），物流已生效

## S2 组群竞价
- 组群 invite 跨云超时 → **RPC 盲标回退**
- 有效出价 2：`supplier-a@13.5` / `supplier-c@15.0` → 选 A
- 订单 `tk-ord-ase-56960216-supplier-a-M-CASTER-200` 货款 6750
- 三方确认：buyer/supplier/logistics ack → `case-56960216` **ACTIVE**
- 截图：供应商A 订单+物流已生效；物流台 `tk-log-a-M-CASTER-200` 已生效；采购商审计条目 closed

## 关键修复
1. buyer wit 指令禁止对含 `{}` 文本 `.format()`（避免 KeyError 崩溃）
2. 订单工单标题优先 `order_draft` 产品摘要
3. `step_auction`：无有效定价出价时强制 RPC blind-bid 回退

## 残留风险
- 组群 MQ invite 对阿里云供应商仍不稳定；业务正确性依赖 RPC 回退

## 最终交付
- 保留证据包：`docs/evidence/e2e_thinking_chain/final_best/`
- Word 报告：`docs/evidence/e2e_thinking_chain/reports/AgentLink_E2E_双场景验收证据包_20261029.docx`
