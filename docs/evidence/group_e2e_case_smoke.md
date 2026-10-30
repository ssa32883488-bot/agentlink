# Group 完整 case 冒烟

**日期**：2026-10-27  
**脚本**：`scripts/_smoke_group_e2e_case.py`  
**结论**：PASS

## 链路

| 步骤 | 结果 |
|------|------|
| 发现 | `platform_adp`，候选 3 |
| 短名单 | supplier-a/b/c |
| RFQ | `COMPARE_PENDING`（本轮 quotes=0，未阻塞后续） |
| 组群竞价 | `transport=group`，3 出价 + 3 TCO 方案 |
| 选商下单 | `ORDER_DRAFT`，supplier-a，运费 276 已写入草案 |
| 工单 | `tk-ord-ase-13804fca` |

## 最优方案

- supplier-a：单价 38.58 · 运费 276 · **TCO 19566**（500 件）
