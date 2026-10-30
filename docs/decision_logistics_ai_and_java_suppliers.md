# 决策：物流「+AI」程度 · 供应 Java Agent 框架

> 日期：2026-10-28  
> 输入：物流要能独立理解多样结构化需求并按既定规则算准运输方案；供应 Java 框架由可实现性选型。

---

## 一、物流智能体 · 「+AI」定到哪一档

### 定位（拍板）

**独立 Partner 智能体（Python）**：接收来自采购/供应商的**各种结构化运力需求**，归一成规范询运单，再严格按你给定的运费矩阵算出**准确、可复现**的运输方案（可多档对比 + 推荐一档）。

不是「聊天客服」，也不是「LLM 自己编运费」。

### 能力分层（硬约束）

| 层 | 谁做 | 做什么 | 禁止 |
|----|------|--------|------|
| **理解 / 归一** | AI（可选 LLM + 确定性映射） | 把残缺/异构字段（sku、件数、包装、urgency、邮编、发到城市、服务偏好…）补全/映射为标准 `shipping_request` | 不得直接产出金额 |
| **计价真相** | **纯规则引擎**（现有 `policy.yaml` + `seat_catalog`） | 计费重、服务档、路线系数 → 运费 / ETA / breakdown | LLM **不得**改价、改系数 |
| **方案输出** | 规则单档计价 | **默认只回最经济一档（economy）**，缩短流程；调用方显式指定 `service_level` 时才用该档 | 不得擅自升舱加价 |

### 输入多样性（要覆盖）

调用方可能只给其中一部分，物流侧负责归一或 `awaiting-input` 澄清：

- 重量 / 体积 / 物料码（从 catalog 推体积与抛货）
- 件数 × 单件包装
- 起讫：城市 / 邮编 / lane
- 时效意图：`urgency` / `service_level` / 「三天内到」
- 约束：最大预算（可选 soft）、不可用服务档

### 输出形态

维持单条 `agentlink.shipping_quote`（一请求一方案）：

- **未指定** `service_level` → 固定选 **economy（经济拼车）**
- **已指定** express / standard / economy → 按指定档计价
- 回执含 `service_level` / `service_label` / breakdown，便于审计

### 与现状差距

| 已有 | 待补 |
|------|------|
| 单档规则计价、路线系数、计费重 | 默认档改为 economy；强化异构字段归一 |
| 部分字段归一（sku→体积） | 缺字段 `awaiting-input` 澄清 |
| 几乎无 LLM | 可选：结构化理解辅助（**不碰数字**） |

**结论**：物流 = **规则引擎算准 + 默认最经济单方案**；AI 只辅助理解多样结构化输入，不扩展成多方案比选（刻意减流程）。

---

## 二、供应智能体 · Java 框架选型（可实现优先）

### 仓库事实

- 本仓 **无 Java 代码**、**无 acps Java SDK**（仅有 Python `acps-sdk`）。
- 异构演示要求：供应侧换语言，但 **AIP 信封 / ACS / AMP 语义** 与现网兼容。

### 选型（拍板）

| 组件 | 选择 | 理由 |
|------|------|------|
| 应用框架 | **Spring Boot 3** + Java 17 | 主流、我能稳定交付 REST/`/rpc` |
| Agent / AI | **LangChain4j** + OpenAI 兼容（DeepSeek） | `@AiService` + `@Tool` 最贴合「议价话术调工具」；与采购侧「模型调 Tool」叙事对称 |
| 计价 / 促销 / 库存 | **纯 Java 规则服务**（移植 `promo` / catalog） | 金额与门槛不许模型编造 |
| 协议接入 | **自研轻量 AIP Partner 适配层**（对照 Python `partner_app` + StructuredDataItem） | 无官方 Java SDK 时的务实路径；对外仍是同一套 schema |
| 配置 | `application.yml` + 与 Python 同源的 JSON/YAML 运营参数 | `seat_catalog` / 促销可抽共享文件 |

**不选**：Spring AI（生态可，但 LangChain4j 的 Tool Agent 路径更成熟、文档更贴「供应商调价工具」）；纯规则无 LLM（削弱「Java+AI」异构叙事）。

### 供应侧 AI 浓度（建议）

与物流类似，**钱走规则，话走模型**：

- Tools：`price_from_catalog`、`apply_promo`、`check_inventory`、`attach_freight`（HTTP 调物流 AIP）、`build_quote`
- LLM：理解议价目标、选 Tool、生成 `talk_track` / `counter_options` 文案
- 禁止：模型直接写 `unit_price` / `shipping_cost`

### 落地状态（A/B/C 已竖切跑通）

目录：`java-suppliers/`（Spring Boot 3 + LangChain4j + AIP `/rpc` 适配）。

| 步骤 | 状态 |
|------|------|
| 共享模块 catalog/promo + AIP | 已完成 |
| A/B/C 三进程初轮报价 | **冒烟 PASS**（`scripts/smoke_java_suppliers.py`） |
| 议价 / 竞价 / 合同确认 schema | 已接入管线 |
| 被动询运合入 | 待补（可先 `need_freight=false`） |
| ACS endpoint 切 Java | 本地已占 8011/8013/8014 |

启动：`scripts/start_java_suppliers.ps1`  
上线：`scripts/_deploy_full_java_suppliers.py`（腾讯采购/物流 + 阿里 Java 覆盖）· 切流 `scripts/_finish_java_supplier_cutover.py`  
冒烟期望：脚轮 500 → 单价 **18.0**；B 面料 35；C 椅架 100；`runtime=java-langchain4j`。

**线上状态（2026-10-28）**：阿里云 `39.105.20.113:8011/8013/8014` 已由 Java 覆盖 Python；公网 HTTPS 冒烟 **PASS**；腾讯云采购/物流已推送座椅参数与 economy 默认档。

---

## 三、六员目标栈（To-Be）

| 智能体 | 语言 | AI | 金额真相 |
|--------|------|-----|----------|
| buyer-a / buyer-b | Python | Wit + DeepSeek | ERP / 方案层 |
| logistics | Python | 结构化理解 + 方案说明（可选 LLM） | **运费规则引擎** |
| supplier-a/b/c | **Java** | **LangChain4j** + DeepSeek | **catalog + promo 规则** |

---

## 四、已确认

1. 物流：**默认最经济单方案（economy）**，只回一条报价，减流程。  
2. 供应：**A/B/C 全部上 Java 并跑通**。
