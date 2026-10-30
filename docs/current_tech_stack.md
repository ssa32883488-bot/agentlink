# AgentLink 当前技术栈整理（As-Is）

> 日期：2026-10-28（基线）· **业务主路径更新见 2026-10-30 [`commerce_v2_asbuilt.md`](./commerce_v2_asbuilt.md)**  
> 范围：本仓库 `项目开发/agentlink` 六智能体 + 共享运行时 + UI  
> 用途：讨论异构改造（采购/物流 Python+AI · 供应 Java+AI）前的现状基线
>
> **注意**：采购对话/双路径编排已切到 `commerce_v2`（`AGENTLINK_RUNTIME=v2`）。下文 §3.1 中 Wit 主路径描述为历史基线；以 `commerce_v2_asbuilt.md` 为准。

---

## 1. 一句话结论

**现状：六个智能体全部是 Python 单体仓。**  
采购侧（buyer-a/b）已是「Wit + DeepSeek」强 AI 编排；供应商与物流对外是 **AIP Partner 确定性管线**（规则图 + policy），对话侧可选轻量 LLM；协议平面统一走 **acps-sdk（ADP/AIP/AMP）**。

目标异构（采购+物流 Python · 供应 Java）**尚未落地**——供应侧目前与物流同构，都是 `build_partner_app` + Python graph。

---

## 2. 共享底座（全员）

| 层 | 现状 | 关键位置 |
|----|------|----------|
| 语言 / 运行时 | Python **≥3.12** · uv / venv | `pyproject.toml` |
| HTTP | **FastAPI** + **uvicorn** | 各 `agents/*/main.py` |
| 协议 SDK | **acps-sdk**（本地 editable） | ADP 发现 · AIP `/rpc` · AMP Kafka |
| 配置 | YAML policy + `.env` | `agents/*/policy.yaml` · `config/` |
| 业务数据 | **SQLite** 每智能体一库 | `data/{agent}.sqlite3` · `commerce/db.py` |
| 主数据 / 运营参数 | 座椅 catalog + seed | `commerce/seat_catalog.py` · `seed.py` |
| 商户 / 车道 | YAML | `commerce/merchant_profiles.yaml` |
| 可观测 | AMP 心跳 + access/message | `commerce/amp_log.py` · Kafka |
| UI | 静态 HTML/JS（无 React/Vue） | `ui/static/` · 端口 8080/8090/8091… |
| 依赖声明 | `fastapi` `httpx` `pydantic` `pyyaml` `openai` `wit-framework` `langgraph*` | `pyproject.toml` |

\* `langgraph` / `langchain-core` 在依赖里，**业务 Partner 管线并未用 StateGraph**；实际是手写 `graph.py` pipeline。AGENTS.md 里「LangGraph」属规划/遗留表述，与 as-built 不一致。

---

## 3. 按智能体拆开（As-Is）

### 3.1 采购商 A / B · `buyer-a` · `buyer-b`

| 维度 | 内容 |
|------|------|
| 角色 | Leader：对话编排 · ERP · 经 ADP 发现 · AIP 调 Partner |
| 进程形态 | 自建 FastAPI（非 `build_partner_app`） |
| AI 栈 | **Wit Framework 2.1** + **OpenAIChatProvider** → DeepSeek（OpenAI 兼容） |
| 入口 | `commerce/chat_buyer_wit.py` · `BUYER_CHAT_ENGINE=wit` |
| 能力 | `@capability`：erp.* / flow.* / discover / rfq / 议价 / 方案等 |
| 领域 | 采购案状态机 · HITL · 方案推演 `scheme_planner` |
| 本地能力 | ToolGateway · MemoryStore · SQLite 商城/BOM/库存 |
| 端口（示意） | A `8010` + UI `8090` · B `8012` + UI `8092` |

**AI 浓度：高**（多轮工具调用是主路径）。

### 3.2 物流 · `logistics`

| 维度 | 内容 |
|------|------|
| 角色 | Partner：运费 / ETA / 服务档 |
| 进程形态 | `agentlink_runtime.partner_app.build_partner_app` |
| AI 栈 | **基本无 LLM**；确定性计价 |
| 管线 | `agents/logistics/graph.py`（计费重 · 服务档 · 路线系数） |
| 策略 | `agents/logistics/policy.yaml` |
| 端口 | `8015/rpc` |

**AI 浓度：低**（规则引擎）。你规划里归「Python+AI」时，需要明确：补对话/异常解释 LLM，还是仅保留 Python 规则 + 协议。

### 3.3 供应商 A / B / C · `supplier-*`

| 维度 | 内容 |
|------|------|
| 角色 | Partner：报价 / 议价 / 竞价 / 合同确认 + 被动询运 |
| 进程形态 | 同物流：`build_partner_app` |
| AI 栈 | **报价主路径无 LLM**；门户对话 `commerce/chat_supplier.py` 可选用 OpenAI 兼容补话术 |
| 管线 | `agents/supplier_{a,b,c}/graph.py` + `supplier_common/{promo,freight,negotiate,catalog_price}` |
| 差异 | A 价格优先 · B 定制+MOQ · C 紧缺替代/分批 + 跨省补贴 |
| 端口 | A `8011` · B `8013` · C `8014`（各 `/rpc` + 管理 UI） |

**AI 浓度：低～中**（业务确定性，对话可选 LLM）。  
**与目标差距最大**：目标要迁到 **Java+AI**，协议边界仍须兼容现有 AIP 信封与 ACS。

---

## 4. 分层示意（现状）

```
┌────────────────── UI（static JS）──────────────────┐
│  商城 8080 · 采购后台 8090/8092 · 供应后台 8091…     │
└────────────┬───────────────────────┬───────────────┘
             │ REST/SSE                │ REST
     ┌───────▼───────┐         ┌───────▼────────┐
     │ buyer FastAPI │         │ partner FastAPI │
     │ Wit+DeepSeek  │         │ build_partner   │
     │ tools/ERP     │         │ + graph.py      │
     └───────┬───────┘         └───────┬────────┘
             │ AIP/ADP/AMP               │ AIP/AMP
             └──────────► 梧桐平台 / Kafka ◄┘
```

---

## 5. 协议与异构约束（讨论时不要动的面）

无论供应是否改 Java，对外应保持：

| 协议 | 用途 | 现状实现 |
|------|------|----------|
| **ADP** | 发现候选 Partner | `commerce/discovery.py` → 平台 + 本地 ACS |
| **AIP** | `/rpc` 任务信封（quote / bargain / shipping…） | acps-sdk · `wrap_business` |
| **AMP** | 心跳与消息审计 | Kafka topics |
| **ACS** | 登记卡片 | `acs/*.acs.json` |

异构成立条件：**同一信封 schema + 同一 AIC/证书语义**；内部语言可换。

---

## 6. 目标对照（你的计划 vs 现状）

| 智能体 | 你的目标 | 现状 | 差距 |
|--------|----------|------|------|
| buyer-a / buyer-b | Python + AI | Python + Wit/DeepSeek | **已对齐方向**；可继续加深工具/方案 |
| logistics | Python + AI | Python + 规则计价 | 缺「AI」叙事/能力；需定要加什么 |
| supplier-a/b/c | **Java + AI** | Python + 规则图（+可选对话 LLM） | **整栈迁移**；需定 Java 侧 Agent 框架与 acps Java SDK 是否就绪 |

---

## 7. 已拍板方向（详见决策文）

见 `docs/decision_logistics_ai_and_java_suppliers.md`：

1. **物流**：独立 Partner；默认 **economy 单方案**；AI 做结构化归一，**运费由规则引擎算准**。  
2. **供应**：`java-suppliers/` · Spring Boot 3 + **LangChain4j** + DeepSeek；A/B/C 本地 **8011/8013/8014 冒烟 PASS**；金额走规则；AIP 轻量适配层。

---

## 8. 相关文档

- 运营参数：`docs/six_agents_tech_stack_and_params.md`  
- 采购 As-Built：`docs/design_buyer_a_agent_asbuilt.md`  
- 供应商优惠：`docs/supplier_profiles_and_promotions.md`  
- 门户端口：`docs/agent_portals.md`
