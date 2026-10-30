# 议价策略 · 满减 / 跨省补贴 / 多方案

**版本**：2026-10-27  
**目标**：议价像真实谈判，不是死压单价；预算非必填，智能体返回多方案。

## 供应商政策（演示）

| 供应商 | 主套路 | 额外 |
|--------|--------|------|
| A 沧州 | 货价满减两档 | — |
| B 邢台 | 件数满减 + 货价满减 | MOQ 200 |
| C 太原（山西） | 货价满减两档 | **跨省出省运费补贴**（审核不确定） |

## 议价行为

1. 出站 `goal_text` 只谈交期/质量/活动条件，**不含预算数字**。  
2. 供应商回执：小幅善意让价 + `talk_track` + `counter_options`（维持现量 / 凑满减 / 冲补贴）。  
3. 采购侧 `plan_procurement_schemes` 生成 S1/S2/S3，写入 case.`procurement_schemes`。

## 方案与预算姿态

| 姿态 | 怎么来的 | 方案偏好 |
|------|----------|----------|
| 未声明 | 默认 | 按估算 TCO 排序，三类都给 |
| ample（宽裕） | 人自愿说 | 突出凑满减 / 跨省补贴 |
| tight（偏紧） | 人自愿说 | 突出拆单，弱化不确定补贴 |

`soft_budget` 可选，仅打 `within/over_soft_budget` 标签，**永不**作为强制提问。

## 代码入口

- `agents/supplier_common/promo.py` — 满减/补贴结算  
- `agents/supplier_common/negotiate.py` — 议价回执  
- `commerce/scheme_planner.py` — 方案推演  
- `commerce/flow_service.step_negotiate` — 议价后落方案  
