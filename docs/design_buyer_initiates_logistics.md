# 物流订单由采购（订单发起方）联系

**日期**：2026-10-30  
**变更**：订单双边生效后，**采购**询运并生成「采购↔物流」工单；供应侧不再拉承运工单。

## 前后

| | 优化前 | 优化后 |
|--|--------|--------|
| 谁联系物流 | 供应 `_maybe_start_logistics` | **采购** `_maybe_start_logistics` |
| 物流工单对端 | 供应 ↔ 物流 | **采购 ↔ 物流** |
| 确认字段 | `supplier_logistics_ack` | `buyer_logistics_ack`（兼容旧字段） |
| 发货地 | 供应政策城市 | 仍按供应方城市写入询运 origin |

## 关键代码

- `commerce/order_tickets.py` · `_maybe_start_logistics`
- `commerce/logistics_tickets.py` · `quote_and_spawn_from_order` / `ack_logistics`
- `ui/static/app.js` · 采购可确认物流工单

## 手测

1. 采购下单 → 买卖双方确认订单生效  
2. 采购工单待办出现物流订单；物流台出现承运工单（对端 buyer）  
3. 供应侧**不应**再出现新的待确认物流工单  
4. 采购 + 物流双方确认 → 物流生效  
