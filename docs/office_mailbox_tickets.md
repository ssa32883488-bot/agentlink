# 邮箱 · 工单 · 回溯审计

每个智能体独立库内具备：

| 能力 | 说明 |
|---|---|
| 邮箱 | 站内电子邮；首发**电子订单** / **电子发票** |
| 工单待办 | `open` 处理中 |
| 挂起 | `suspended`，固化 `state_json`，可续办 |
| 续办 | 读回挂起时工作状态 → 重回 `open` |
| 完结回档 | 双方均收到最终电子订单 **且** 电子发票后 → `closed` |
| 回溯审计 | `ticket_events` 时间线 + `/api/erp/office-audit` |

## 订单草案 → 双边工单（自动）

采购案进入 `ORDER_DRAFT` 后：

1. 买方 / 选定供应商各生成同号 `kind=order` 工单，并弹出「新订单已生成」通知  
2. 用户进入「工单待办」点击 **确认订单已生成**（双方各自确认）  
3. 双方都确认后，系统自动互发电子订单 + 电子发票到双方邮箱  
4. 双方收妥（四标志齐）→ 工单 `closed` 回档  

## 完结条件

工单完结（完全回档）当且仅当：

- 己方已持有最终电子订单邮件
- 对端已收到最终电子订单邮件
- 己方已持有最终电子发票邮件
- 对端已收到最终电子发票邮件

未完结工单可挂起；挂起后读取 `state` 续办。仅 `closed` 视为回档。

## API（各智能体）

- `GET /api/erp/mailbox`
- `POST /api/erp/mailbox/send`
- `POST /api/erp/mailbox/receive`（对端投递）
- `GET/POST /api/erp/tickets`
- `POST /api/erp/tickets/{id}/suspend|resume`
- `POST /api/erp/tickets/{id}/send-final-docs`
- `POST /api/erp/tickets/mirror-order`（跨云镜像订单工单）
- `POST /api/erp/tickets/{id}/ack-order`（确认订单已生成）
- `GET /api/erp/mailbox/{id}`（订单/发票邮件详情）
- `GET /api/erp/tickets/{id}`（工单详情含事件）
- `GET /api/erp/order-provenance?case_id=&ticket_id=`（代码级全链路 + 梧桐 ADP/AMP/AIP）
- `GET /api/erp/order-provenance/list`
- `GET /api/erp/office-audit`
- `GET /api/erp/notifications`（供应侧通用通知；采购侧沿用原路由）

## 审计全链路内容

点选订单后展示：

1. **代码级成立链路**：各阶段对应模块（`discovery` / `aip_client_util` / `order_tickets` / `mailbox` 等）及命中事件  
2. **梧桐 ADP**：发现 URL、查询词、候选 AIC  
3. **AMP Access/Message**：本地 `amp_*.jsonl`（已上报 Kafka `amp.access` / `amp.message`）  
4. **AIP RPC**：`logs/interactions.jsonl` 本机交互  
5. **电子订单/发票**：可再点开单据详情
