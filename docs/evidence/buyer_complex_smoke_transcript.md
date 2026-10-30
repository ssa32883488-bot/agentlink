# 复杂任务冒烟实录（2026-10-26）

来源：线上 `POST /api/erp/chat/stream` 六轮对话（`scripts/_smoke_buyer_complex_chat.py`）  
案件：`case-d31de9b5` → 终态 **ACTIVE**

## 总览

| 轮 | 用户意图 | Agent 实际调用的 Tools | 结果要点 |
|---|---|---|---|
| 1 | 查库存与通知，判断是否采购 | `erp.query_inventory` → `erp.query_notifications` | 多原料低于安全线；建议可启正式采购 |
| 2 | 建案 + 只发现不询价 | `flow.start_case` → `flow.discover` | `SHORTLIST_PENDING`；平台 ADP，三家平台命中 |
| 3 | 确认三家并询价对比 | `flow.status` → `flow.hitl_decide` → `flow.confirm_shortlist_and_rfq` | 三家报价入库，进入对比待决策 |
| 4 | 不要下单，先议价 | `flow.status` → `flow.decide_negotiate` | 经 AIP 与 A/B/C 议价，更新对比 |
| 5 | 最优下单 + 物流合同 | `flow.status` → `flow.decide_order` → `flow.shipping_contract` | 选 **supplier-a**；合同待双边确认 |
| 6 | 采购确认→供应商确认→激活 | `flow.status` → `flow.confirm_buyer` → `flow.confirm_supplier` → `flow.activate` | **ACTIVE** |

## 体现的 Agent 行为（非定死脚本）

1. **先观察再规划**：第 1 轮只查 ERP，未强行 discover。  
2. **遵守用户约束**：第 2 轮「不要直接询价」→ 只 `start_case`+`discover`。  
3. **路径分叉**：第 4 轮按要求走议价，而非最短「直接下单」。  
4. **HITL**：第 3 轮显式 `flow.hitl_decide` 后再询价。  
5. **闭环**：第 6 轮按人指令完成双边确认与激活。

## 工具调用序列（机器可读）

```text
T1: erp.query_inventory, erp.query_notifications
T2: flow.start_case, flow.discover
T3: flow.status, flow.hitl_decide, flow.confirm_shortlist_and_rfq
T4: flow.status, flow.decide_negotiate
T5: flow.status, flow.decide_order, flow.shipping_contract
T6: flow.status, flow.confirm_buyer, flow.confirm_supplier, flow.activate
```

完整 reply / case 快照见 `buyer_complex_smoke.json`（若由对话审计恢复）。
