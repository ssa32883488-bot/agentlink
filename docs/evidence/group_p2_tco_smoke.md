# Group P2 TCO 冒烟证据

**日期**：2026-10-27  
**结论**：PASS

## 结果摘要

| 供应商 | 单价 | 运费 | TCO（500件） | 发货地 |
|--------|------|------|--------------|--------|
| supplier-a | 38.58 | 276.0 | **19566.0** | 沧州 |
| supplier-c | 41.75 | 340.2 | 21215.2 | 太原 |
| supplier-b | 46.14 | 337.5 | 23407.5 | 邢台 |

- 传输：`wt.ioa.pub` Group（盲拍 + 同组 `shipping_request`→物流）
- 目的地邮编：`071000`（保定）
- 脚本：`scripts/_smoke_group_p2_tco.py`

## 下单数据源

`step_decide(order)` 在 `BID_REVIEW` 优先读 `auction_summary.schemes` / `auction_bids`，再回退 RFQ `quotes`。
