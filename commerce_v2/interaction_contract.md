# commerce_v2 交互契约

> 与 As-Built 对齐：[`docs/commerce_v2_asbuilt.md`](../docs/commerce_v2_asbuilt.md)（2026-10-30）

## AskUser vs Gate

| 类型 | 入口 | 作用 |
|------|------|------|
| AskUser | 对话 `choice_actions` / `shortlist_confirm` | 推进业务阶段：短名单、议价、买法、组群确认 |
| Gate | `/api/erp/tickets/{id}/ack-order` / `ack-logistics` | 只写确认态；双方 ack 后 `effective=true` |

对话不得声称订单已生效；以工单 `buyer_ack`/`supplier_ack`/`effective` 为准。

## UI Widget

- `shortlist_confirm`：断点①；提交话术含 `candidate_id` + `rfq.send_batch`（普通）或「确认组群竞价」（组群）
- `choice_actions`：议价/买法/组群决断；`message` 原样回灌 chat
- 组群聊天室：`#groupRoomModal`；用户收起后轮询不得强弹；可「展开组群聊天室」

## 多品需求（硬约束）

- `brief.items[]` 为权威行项目；用户同时点名多品类（脚轮+坐垫+…）**禁止丢项**
- 防幻觉：仅当用户**未提**脚轮却改写成脚轮时拦截；多品并存时保留脚轮行
- 发现：`discover_suppliers_for_brief` 按全部 SKU **并集**召回
- 组群报价：按供应目录能力 **按行** `v2.group_bid`；汇总须 `covers_all` 或明确标 `missing`

## 普通十点（摘要）

需求改写(+items) → 发现(并集) → 短名单确认（未确认不发 RFQ）→ 初报 → 议价 Ask → 买法 Ask → 共享订单（`place_order=on`）→ 双边 Gate → 物流 Ask → 物流工单 Gate → ACTIVE

## 组群

采购主持；断点①确认开群（可选物流）；优先国标 Group MQ（`transport=group`）；邀请自签 HTTPS 可用 `AIP_SSL_INSECURE`；MQ/AIP 卡住可本地续跑；货清后拉物流；系列工单。  
下单：供应工具 `place_order` 仅当信封 `place_order=on`；物流确认闸使用 logistics ticket id。
