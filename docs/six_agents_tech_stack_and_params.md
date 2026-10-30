# 六智能体 · 技术栈、定位与运营参数

**对齐文档**：《6agent的技术设计.docx》（后台运营参数）  
**场景**：座椅加工生产协作（采购 ↔ 供应 ↔ 物流）  
**统一协议**：ADP（发现）/ AIP（会话任务）/ AMP（心跳与指标）  
**主数据**：`commerce/seat_catalog.py` · 种子 `commerce/seed.py` · 商户 `commerce/merchant_profiles.yaml`

---

## 总览

| 智能体 | 业务实体 | 角色 | 异构栈侧重点 | 策略标签 / 运营要点 |
|--------|----------|------|--------------|---------------------|
| buyer-a | 保定家具厂 | 高档座椅采购 | FastAPI + Wit/DeepSeek + 工具网关 + SQLite ERP | 重型脚轮/记忆海绵/高档面料 |
| buyer-b | 承德办公家具制造厂 | 平价办公/家用采购 | 同构买家骨架，策略更省 | 标准脚轮/普通海绵面料 |
| supplier-a | 沧州组件厂 | 五金结构件供应 | 确定性 graph + catalog 计价 + 被动询运 | `price-first` · 脚轮满 500 九折 |
| supplier-b | 邢台软装厂 | 面料/海绵供应 | 同构供应 pipeline，强制定制字段 + MOQ | `custom-moq` · 货价满 1 万减 1000 |
| supplier-c | 太原组件厂 | 结构件/软垫 · 紧缺 | 替代 SKU + 分批履约 + 跨省补贴 | `scarce-substitute` · 椅架满 500 打 8.5 折 + 跨省运费半补 |
| logistics | 采联智运 | 全国连锁物流 | 确定性询运图 · 服务档 × 路线系数 | 计费重=实重/体积重取大 |

**技术栈 As-Is / 异构目标**：见 `docs/current_tech_stack.md`（现状六员皆 Python；目标拟供应侧迁 Java+AI）。  
**异构含义**：实现语言与编排可不同，对外一律 ADP/AIP/AMP + ACS。

---

## 单椅 BOM（全场共用）

扶手×1 + 五星脚×1 + 脚轮×5 + 气压棒×1 + 钢管制件椅架×1 + 海绵×1 + 面料×1  

编码：`RM-ARMREST`（文档空格已归一）、`RM-BASE-NYLON`、`RM-GASLIFT`、`RM-TUBE-STEEL`、`RM-CASTER-300/200`、`RM-FOAM-MEM/STD`、`RM-FABRIC-PRO/STD`。

---

## 采购商 A · buyer-a

| 项 | 内容 |
|----|------|
| 技术栈 | FastAPI · `commerce/chat_buyer_wit.py`（Agents SDK）· ToolGateway · MemoryStore · SQLite（产品/BOM/库存） |
| 入口 | `agents/buyer_a/main.py` · 商城/ERP `mount_buyer_commerce` · 采购流 `mount_procurement_flow` |
| 运营参数 | `agents/buyer_a/policy.yaml` · 种子物料见 `BUYER_A_*` |
| 成品 | CHAIR-PRO / CHAIR-EXEC |
| 安全库存告警倾向 | 气压棒 `RM-GASLIFT` 常低于安全线 |

---

## 采购商 B · buyer-b

| 项 | 内容 |
|----|------|
| 技术栈 | 与 A 同构买家骨架（独立 AIC / DB） |
| 运营参数 | `agents/buyer_b/policy.yaml` · `BUYER_B_*` |
| 成品 | CHAIR-ECO / CHAIR-HOME |
| 物料档 | `RM-CASTER-200`、`RM-FOAM-STD`、`RM-FABRIC-STD` |

---

## 供应商 A · supplier-a（沧州组件厂）

| SKU | 目录价 | 可售（演示） |
|-----|--------|--------------|
| RM-ARMREST | 30 | 600 |
| RM-BASE-NYLON | 40 | 500 |
| RM-GASLIFT | 50 | 400 |
| RM-CASTER-300 | 20 | 2000 |
| RM-CASTER-200 | 15 | 2500 |
| RM-TUBE-STEEL | 85 | 300 |

**定价**：无私下底价；挂牌价不议。  
**优惠**：脚轮（300/200）单品满 **500** 件 → 该单品总价 **九折**（`line_qty_discount`）。  
**栈**：`agents/supplier_a/graph.py` + `pricing.py` + `supplier_common/{promo,freight,negotiate,catalog_price}`；线上供货主路径为 Java。

---

## 供应商 B · supplier-b（邢台软装厂）

| SKU | 目录价 | MOQ |
|-----|--------|-----|
| RM-FABRIC-PRO | 35 | 50 |
| RM-FABRIC-STD | 12 | 50 |
| RM-FOAM-MEM | 55 | 20 |
| RM-FOAM-STD | 20 | 20 |

**定价**：无私下底价；挂牌价不议。  
**优惠**：任意软装组合货价满 **10000** 减 **1000**。  
**栈**：定制字段 `material`/`color` 校验 + MOQ 拒报。

---

## 供应商 C · supplier-c（太原组件厂）

| SKU | 目录价 | 可售 |
|-----|--------|------|
| RM-ARMREST | 35 | 200 |
| RM-BASE-NYLON | 35 | 180 |
| RM-TUBE-STEEL | 100 | 120 |
| RM-CASTER-200 | 15 | 800 |
| RM-FOAM-MEM | 50 | 150 |
| RM-FOAM-STD | 20 | 200 |

**定价**：无私下底价；挂牌价不议。  
**优惠**：`RM-TUBE-STEEL` 满 **500** → **8.5 折**；跨省运输运费补贴 **50%**（审核不确定）。  
**栈**：库存不足时给替代/`split_fulfillment_plan`。  
**采购议价**：`bargain_room` / 方案推演只基于上述优惠政策（凑门槛、拆单），不再压私下底价。

---

## 物流 · logistics（采联智运）

| 服务 | 时效 | 起步（首 100kg/1 方） | 续费 |
|------|------|----------------------|------|
| express 极速达 | 1–2 天 | 350 | 1.5 元/kg 或 300 元/方 |
| standard 标准快线 | 3–4 天 | 180 | 0.8 / 150 |
| economy 经济拼车 | 5–7 天 | 80 | 0.4 / 80 |

**计费**：实际重 vs 体积重取大；抛货（面料/海绵）1 m³=200 kg。  
**路线系数**：≤300km ×1.0 · ≤800km ×1.2 · 更远 ×1.5。  
**实现**：`agents/logistics/graph.py` + `seat_catalog.chargeable_weight_kg` / `route_factor`。

---

## 配置落点（改运营参数改这里）

| 文件 | 作用 |
|------|------|
| `commerce/seat_catalog.py` | 物料主数据、BOM、供应目录、促销结构、物流矩阵 |
| `commerce/seed.py` | 写入买家/卖家 SQLite |
| `agents/*/policy.yaml` | 各智能体运行时策略与促销 |
| `commerce/merchant_profiles.yaml` | 商号、地址、车道里程 |
| `agents/supplier_common/promo.py` | 满量折扣 / 满减 / 跨省补贴结算 |

重置种子：

```bash
python -m commerce.seed
```
