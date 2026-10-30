# 双路径采购 · 组群竞价 · 六智能体智能化

**日期**：2026-10-28  
**目标**：常规询价路径与组群竞价路径都可走通；业务判断「适合组群」时**让用户选择**，不自动开拍。

> **2026-10-30 实现状态**：主路径已迁到 `commerce_v2`（非本文早期 Wit `flow.decide_auction` 草案）。  
> 请以 [`commerce_v2_asbuilt.md`](./commerce_v2_asbuilt.md) 与 [`design_two_paths_interconnect.md`](./design_two_paths_interconnect.md) §8 为准；本文保留作早期方案备忘。

---

## 1. 组群竞价的业务目的

需求较丰富、短名单多方可比时，经多家供应 + 物流旁听协商（盲拍 + TCO），给出**更经济、更合适各方**的订货方案。  
不是默认主路径，而是比价后的可选升级机制。

---

## 2. 两条路径

```
发现 → 短名单 HITL → 并行 RFQ
                │
                ▼
         COMPARE_PENDING
                │
     ┌──────────┼──────────────────┐
     │          │                  │
  路径甲      路径乙（适合时出现）   路径丙
  议价        组群竞价              直接选商
  negotiate   auction               order
     │          │                  │
     ▼          ▼                  ▼
  方案按钮   BID_REVIEW(TCO方案)   ORDER_DRAFT
     └──────────┴──────────────────┘
                      │
                      ▼
              双边订单工单 → 确认 → 电子订单/发票
```

- **路径甲**：一对一/少家谈满减门槛与补贴。  
- **路径乙**：多家密封盲拍 + 物流 TCO，再人选方案。  
- **路径丙**：RFQ 已够清楚，直接下单草案。

---

## 3. 何时「适合组群」并展示选项（判定，非强制）

同时倾向满足：

1. 短名单有效报价家数 **≥ 2**（建议 ≥ 3 更贴「多方」）  
2. 同一 `product_name` / 规格可对齐（一案一主体）  
3. 量或金额有一定体量（如 qty≥200 或货价跨度值得再竞）  
4. RFQ 结果胶着：最低与次低 grand_total 差距相对小，或运费占比高需 TCO  
5. 用户未指定独家供应商  

**不适合**：独家、规格不对口、纯促销凑门槛已明显最优、多 SKU 未拆案。

判定结果写入工具回执 `auction_suitability`；仅当 `offer=true` 时，比价按钮里出现「发起组群竞价」。

---

## 4. 六智能体智能化分工（运行时）

| 智能体 | 智能化要点 | 组群中的角色 |
|--------|------------|--------------|
| buyer-a/b | Wit 规划 + 工具；适合时出竞价按钮；执行 decide+run auction | Leader 建组、收方案、人确认后选商 |
| supplier-a/b/c | 对话 Wit；金额规则管线；认 `blind_bid` → `blind_bid_offer` | 组成员出价 |
| logistics | 结构化归一 + 规则计价 | 进组旁听、`bid_skip`、支撑 TCO |

钱走规则，话走模型；竞价公平性不依赖 LLM 临场改价。

---

## 5. 落地清单（本迭代）

1. `commerce/auction_suitability.py` — 适合度判定  
2. `choice_actions.post_quote_choices` — 适合时加入组群竞价按钮  
3. Wit 恢复 `flow.decide_auction` + `flow.run_auction`  
4. 提示词：双路径说明；禁止未勾选自动开拍  
5. RFQ / compare 回执带 `auction_suitability`  
