# 采购商 A（buyer-a）Agent 设计文稿 · 现状 As-Built

> 版本：2026-10-26  
> 范围：线上实现（Wit + DeepSeek + Capability Tools + 采购编排/ACPs）  
> 入口：`https://ashui.online:8010` / UI `https://81.70.46.119:8090/`  
> 冒烟实录：`docs/evidence/buyer_complex_smoke.json`（跑完后回填）

---

## 1. 定位与边界

| 项 | 说明 |
|---|---|
| 角色 | 采购侧 **Leader** 智能体：对内查 ERP，对外经梧桐 ADP 发现、经 AIP 调供应商/物流 Partner |
| 对话引擎 | `BUYER_CHAT_ENGINE=wit` + DeepSeek（OpenAI 兼容） |
| 核心文件 | `commerce/chat_buyer_wit.py`、`commerce/flow_service.py`、`commerce/buyer_routes.py` |
| 非目标 | 不是固定 10 步剧本；不替用户自动成交；不编造库存/报价 |

Agent 按**用户本轮意图**规划：先选工具、执行、观察结果，再决定是否继续调工具或回复。  
采购案状态机（`procurement_case.py`）只约束**副作用合法性**（例如未确认短名单不能询价），不强制对话路径。

---

## 2. 总体架构

```
用户（UI 对话）
    │  POST /api/erp/chat/stream  (SSE)
    ▼
buyer_routes.mount_buyer_commerce
    │  stream_buyer_chat_wit(text, run_rfq=…)
    ▼
WitRuntime(WitAgent)  ←── DeepSeek OpenAIChatProvider
    │  astream_events：模型 ↔ 工具多轮
    │  capabilities = erp.* + flow.*
    ▼
┌─────────────┬──────────────────────────────────────┐
│ ERP 本地     │ 跨智能体 / 协议平面                      │
│ buyer_service│ flow_service → discovery(ADP)          │
│              │              → aip_start_structured(AIP)│
│              │              → amp_log(Kafka AMP)       │
└─────────────┴──────────────────────────────────────┘
```

- **规划层**：LLM（Wit Agent Loop）  
- **能力层**：`@capability` 注册的 Tools  
- **领域层**：采购案状态机 + HITL 门禁  
- **协议层**：ADP / AIP / AMP / mTLS（不改报文结构）

---

## 3. Agent 循环如何实现

### 3.1 Wit 运行时（框架）

使用 `wit` SDK：

- `WitAgent(id, instructions, model, capabilities, amp_hooks)`
- `WitRuntime(agent, workspace=workspaces/buyer-a-wit)`
- 单次用户输入：`runtime.astream_events(text)`

`RunConfig`（框架默认）关键字段：

- `max_steps`：单次 run 最大规划步数（框架侧；scoped 路径默认可见为 8）
- `tool_timeout_seconds`：单工具超时
- 产出 `RunResult`：`output_parts`、`observations`、`iterations`、`status`

循环语义（ReAct 风格，由 Wit `_run_core` 实现）：

```
用户消息进入 AgentState
loop (step < max_steps):
  1. 调 LLM（带 instructions + tools schema + 历史）
  2. 若返回 tool_calls → 执行对应 capability → 观察结果写回 messages
  3. 若返回最终文本 → 结束
发出流事件：model.* / tool.start|end / step.* / run.end
```

### 3.2 本仓库对流式事件的桥接

`stream_buyer_chat_wit`：

1. 落库用户话：`bs.append_conversation("user", text)`
2. `_build_runtime(run_rfq)` 每次请求新建 Runtime（能力闭包绑定当前 `run_rfq`）
3. 并行消费：
   - Wit `astream_events`
   - `progress` 队列（发现/询价过程中的中文 status）
4. 映射为前端 SSE：

| SSE type | 含义 |
|---|---|
| `status` | 思考中 / 工具中 / 进度文案（`phase`: think\|tool\|tool_done\|adp\|aip\|…） |
| `token` | 最终回复流式字 |
| `done` | 完整 reply + case_id/state/hitl |
| `error` | LLM/运行失败 |

5. `_finalize_from_run`：从 observations 提取快捷 RFQ、附带当前 `case_id`，写入对话审计。

### 3.3 会话态

- `_ACTIVE_CASE_ID`：进程内当前采购案（多 worker 未共享；演示单实例可接受）
- 正式副作用落在 `data/procurement_cases.json` 状态机

### 3.4 与「定死流程」的关系

| 层 | 是否定死 |
|---|---|
| 对话规划 | **否** — 由模型按意图选工具 |
| Capability 组合 | **否** — 可只查库存、可只发现、可跳过议价 |
| 状态机迁移 | **是（安全）** — 非法迁移抛错，防止未 HITL 就询价/激活 |
| HITL | **是（高风险门禁）** — reject 作废；激活需双边确认 |

---

## 4. Tools（Capability）完整列表

注册处：`commerce/chat_buyer_wit.py` → `_build_capabilities()`。  
共 **16** 个（含已修复注册的 `flow.hitl_decide`）。

### 4.1 ERP / 运营查询

| ID | 参数 | 做什么 | 何时用 | 副作用 |
|---|---|---|---|---|
| `erp.query_inventory` | 无 | 原料库存 + 是否低于安全线 | 用户问库存/是否要补货 | 只读 |
| `erp.query_sales_orders` | `limit=20` | 座椅商城销售订单 | 问订单/销量 | 只读 |
| `erp.query_notifications` | `unread_only=false` | 原料不足等通知 | 问告警/未读 | 只读 |
| `erp.rfq_by_shortage` | 无 | 按缺口对优选供应商快捷 AIP 询价 | 「按缺口补货」且**不要**正式采购案 | AIP 调用；非正式 case |

### 4.2 正式采购编排（flow.*）

| ID | 参数 | 做什么 | 协议/依赖 | 副作用 / HITL |
|---|---|---|---|---|
| `flow.start_case` | `product_name`, `quantity`, `rated_load_kg_min` | 建案 DRAFT，绑定 `_ACTIVE_CASE_ID` | 本地状态机 | 写 case |
| `flow.discover` | `query?` | ADP 发现（平台优先，可容灾标注）→ `SHORTLIST_PENDING` | ADP | 写 candidates；HITL 短名单 |
| `flow.hitl_decide` | `decision`, `agent_ids?`, `note?` | approve/edit/reject/respond | 编排 | reject→EXCEPTION+voided |
| `flow.confirm_shortlist_and_rfq` | `agent_ids` CSV，空=三家 | 确认短名单 + 并行 AIP 询价 | AIP×N + AMP | 报价入库；幂等指纹 |
| `flow.decide_order` | `supplier_agent_id?` 空=最低价 | 生成订单草案 | 本地 | → ORDER_DRAFT |
| `flow.decide_negotiate` | `goal` 文案（禁预算数字） | 议价轮 + 执行 | AIP | → NEGOTIATE_REVIEW |
| `flow.decide_auction` | 无 | 匿名竞价 | AIP | → BID_REVIEW |
| `flow.shipping_contract` | `weight_kg`, `postal_code` | 物流询价并合入合同 | AIP→物流 | → CONTRACT_PENDING |
| `flow.confirm_buyer` | 无 | 采购方签合同 | 本地 | buyer_ack |
| `flow.confirm_supplier` | 无 | AIP 请供应商确认 | AIP | supplier_ack |
| `flow.activate` | 无 | 双边确认后激活 | 本地 | → ACTIVE；否则 403 语义 |
| `flow.status` | 无 | 当前案状态 + HITL | 只读 | 可回填 latest case |

### 4.3 HTTP 对照（非对话，同编排）

对话 Tools 底层即 `flow_service`；也可直调：

- `POST /api/flow/cases`、`.../discover`（`refresh`）、`.../hitl`、`.../rfq`、`.../decide`…  
- `GET /api/flow/metrics` AMP KPI  
- `GET /api/agents/buyer-a/interactions` AIP 协作轨迹  

---

## 5. 系统提示词（规划原则）

见 `INSTRUCTIONS`（摘要）：

1. 按意图规划，不默认走完整链  
2. 事实必须工具，禁止编造  
3. 高风险等人确认（HITL）  
4. 容灾发现必须如实说  
5. 调过 Partner 要点名谁/什么结果  
6. **禁止**固定「步骤 x/10」套话  

---

## 6. 采购案状态机（领域约束）

状态：`DRAFT → DISCOVERING → SHORTLIST_PENDING → SOURCING → COMPARE_PENDING`  
可分支：`NEGOTIATING/BIDDING` → `ORDER_DRAFT → CONTRACT_PENDING → ACTIVE`  
异常：`EXCEPTION`（含 HITL reject 作废）

非法迁移由 `procurement_case.transition` 拒绝——这是**安全约束**，不是对话脚本。

---

## 7. 复杂任务冒烟设计

### 7.1 场景目标

多轮自然语言，迫使 Agent **自行组合**工具：

1. 查库存 + 通知 → 建议是否采购  
2. 建案 + **只发现不询价**  
3. 确认三家询价并对比  
4. **先议价再决策**（非最短路径）  
5. 选商草案 + 物流合同  
6. 双边确认 + 激活  

脚本：`scripts/_smoke_buyer_complex_chat.py`  
产物：`docs/evidence/buyer_complex_smoke.json`（每轮含 user、reply、statuses、tools_timeline、耗时）

### 7.2 实录（已跑通）

| 项 | 结果 |
|---|---|
| 案件 | `case-d31de9b5` |
| 终态 | **ACTIVE** |
| 证据 JSON | `docs/evidence/buyer_complex_smoke.json` |
| 可读实录 | `docs/evidence/buyer_complex_smoke_transcript.md` |

**六轮工具序列（Agent 实际规划）**

1. `erp.query_inventory` → `erp.query_notifications`  
2. `flow.start_case` → `flow.discover`（遵守「不要直接询价」）  
3. `flow.status` → `flow.hitl_decide` → `flow.confirm_shortlist_and_rfq`  
4. `flow.status` → `flow.decide_negotiate`（遵守「先议价」）  
5. `flow.status` → `flow.decide_order` → `flow.shipping_contract`（选 supplier-a）  
6. `flow.status` → `flow.confirm_buyer` → `flow.confirm_supplier` → `flow.activate`  

结论：对话层按用户约束分叉路径；状态机保证激活前双边 HITL；全程到达 ACTIVE。

---

## 8. 关键实现索引

| 主题 | 路径 |
|---|---|
| Agent 循环 + Tools | `commerce/chat_buyer_wit.py` |
| SSE 挂载 | `commerce/buyer_routes.py` |
| 发现 ADP | `commerce/discovery.py` |
| 询价/议价/竞价/物流 | `commerce/flow_service.py` |
| HITL | `commerce/hitl_gate.py` + `step_hitl_decide` |
| AIP 客户端 + AMP send | `agentlink_runtime/aip_client_util.py` |
| Partner 入站 + AMP receive | `agentlink_runtime/partner_app.py` |
| 进度文案 | `commerce/progress.py` |
| UI 消费 SSE | `ui/static/app.js` |

---

## 9. 已知限制

1. `_ACTIVE_CASE_ID` 进程内存：多实例/重启需靠 `flow.status` 回填 latest  
2. Wit 核心为字节码轮子：循环细节以 `runtime.pyi` + 流事件为准  
3. `flow.confirm_shortlist_and_rfq` 把「确认+询价」合成一工具——模型仍可分步（先 status 再决定），但当前能力表未拆成两个独立 tool  
4. 演示依赖 DeepSeek Key 与双云 Partner 在线  

---

## 10. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-10-26 | As-built 首版；去掉强制 10 步套话；补注册 `flow.hitl_decide`；复杂冒烟脚本 |
