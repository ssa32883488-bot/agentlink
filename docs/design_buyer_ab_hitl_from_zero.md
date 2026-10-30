# 采购商 A/B · 人在智能体中（从零设计）

**日期**：2026-10-30  
**范围**：仅采购商 A、采购商 B（一组同构买家）。物流组、供应组另开文档。  
**原则**：Claude Code 式「Ask = 挂起的工具」；确认 = 状态机闸门；**唯一真相在状态，不在嘴上**。

---

## 0. 一句话定位

采购智能体是**替人办事的执行体**；人不是旁观者，而是：

1. **在分叉处做选择题**（AskUser）——决定方向；  
2. **在闸门处做确认**（Gate）——让状态机前进；  
3. **其余时间看投影**——对话只解释状态，不发明状态。

A 与 B：**同一套交互契约与状态机**；差别只在主数据/策略偏好（高档 vs 平价），不在「怎么问人」。

---

## 1. 两层人机接口（禁止混用）

| | **AskUser（澄清题）** | **Gate（确认闸）** |
|--|----------------------|-------------------|
| 语义 | 「你要哪条路 / 缺的偏好是什么」 | 「是否批准这个已成形的动作」 |
| 触发 | 模型调用 `AskUserQuestion` 等价工具，**任务挂起** | UI/工单按钮 → `transition(case/ticket)` |
| 回灌 | `answers` 进 tool_result，再继续推理 | 状态变更事件；模型下一轮**必须读状态** |
| UI | 选项卡（2～4 项，可有推荐、可 Other） | 确认 / 取消（可附摘要，**不是多路径选择题**） |
| 典型 | 议价 vs 竞价 vs 直接下单 | 确认货物订单、确认发起物流询价 |

**铁律**

- 不要用 AskUser 问「你确认订单了吗？」（那是 Gate）。  
- 不要用 Gate 问「要竞价还是议价？」（那是 AskUser）。  
- 模型**禁止**用对话否定 DB/工单已写入的确认结果。

---

## 2. 人在环里的位置（架构）

```text
                    ┌──────────── 人 ────────────┐
                    │  AskUser：选路 / 补偏好      │
                    │  Gate：批订单 / 批物流入口   │
                    └───────────┬────────────────┘
                                │
┌───────────────┐   tool_use    ▼    tool_result / event
│ 对话投影层     │ ◄─────── 采购 Agent Runtime ───────► 工具网关
│ (只读状态叙事) │              │
└───────────────┘              ├── 发现 / RFQ / 议价 / 竞价
                               ├── 案件状态机 (Case)
                               └── 工单状态机 (Ticket) ←── 供应/物流 peer
```

- **Runtime**：唯一编排者；可挂起（Ask）、可推进（工具）、可停在 Gate。  
- **Case**：采购意图与阶段（发现→短名单→询价→比价/竞价→订单→物流入口→…）。  
- **Ticket**：双边确认的权威单据（货单、日后物流单由物流组承接）。  
- **对话**：Case/Ticket 的只读讲解 + 触发 Ask/引导去 Gate；**不是第二套账本**。

---

## 3. 采购案状态机（A/B 共用，极简可演示）

只保留人眼能懂的阶段；名字可映射旧枚举，但**语义以本表为准**。

```text
DRAFT
  → SHORTLIST_PENDING     （已发现，等人勾选供应）          [Gate: 确认短名单]
  → RFQ_SENT              （已询价，等回价）
  → COMPARE               （有报价，可分叉）                [Ask: 路径]
  → ORDER_DRAFT           （已生成货单草案）                [Gate: 采购确认货单]
  → ORDER_PEER_PENDING    （等人家供应确认）
  → ORDER_EFFECTIVE       （双方确认 → 货单生效）
  → LOGISTICS_HINT        （仅提示「去找物流」；不自动下运单）[Gate: 人点「去询运」]
  → (移交物流会话 / 物流组) 
  → ACTIVE / CLOSED
```

**关键修正（针对「确认了还说没有」）**

- 「采购已确认货单」= Ticket 上 `buyer_order_ack=true`（写库）。  
- 「供应已确认货单」= Ticket 上 `supplier_order_ack=true`（写库）。  
- `ORDER_EFFECTIVE` **当且仅当**两边 ack 皆真；对话里出现「已确认」若库中为假 → **以库为准并纠正话术**。  
- 进入 `LOGISTICS_HINT` 的前置条件：**硬依赖** `ORDER_EFFECTIVE`，禁止「嘴上生效」。

---

## 4. AskUser 触发点清单（采购商 A/B）

每条：`何时` · `问什么` · `不问什么` · `答案如何变成动作`。

### A1. 需求歧义（进入发现前）

| | |
|--|--|
| **何时** | 缺物料名/数量/关键规格，且工具无法唯一推断 |
| **问什么** | 例如：脚轮承重档（200 vs 300）、数量档 |
| **不问** | 「要不要开始采购？」（废话 Gate） |
| **回灌后** | 写入 Case.brief → `discover` |

### A2. 短名单确认 —— **这是 Gate，不是 Ask**

勾选供应商 = Gate（可多选 UI），不是 AskUserQuestion。  
（若实现成按钮组，语义仍是 `confirm_shortlist(ids)`。）

### A3. 比价后路径分叉（核心 Ask）

| | |
|--|--|
| **何时** | `COMPARE` 且 ≥2 家可比，或策略上存在互斥路径 |
| **问什么** | 选项示例：`直接下单最优` / `议价一轮` / `组群竞价+TCO`（按场景裁剪到 2～3） |
| **不问** | 「报价看着行吗？」（空泛）；单家可供时不要硬凑竞价 |
| **回灌后** | 唯一 `decide(path)`；禁止并行开多条互斥路径 |

### A4. 不可逆前的偏好（可选 Ask）

| | |
|--|--|
| **何时** | 即将 `ORDER_DRAFT`，且存在非显然默认（交期优先 vs 价优先） |
| **问什么** | 短偏好题；或跳过（A 偏品质、B 偏成本可由策略默认） |
| **回灌后** | 写入 Case.preference，供选供方 |

### A5. 明确禁止的 Ask

- 「是否确认订单」（→ Gate G1）  
- 「供应确认了吗」（→ 读 Ticket，禁止问人猜）  
- 「体积/重量随便估一个」（→ 工具向供应/目录取；holder≠human 则不问）  
- 同一 `question` 指纹重复弹出  

---

## 5. Gate 清单（采购商 A/B）

### G1. 确认货物订单（采购侧）

- **前置**：`ORDER_DRAFT` 且草案字段完整（供方、SKU、数量、单价、货款）。  
- **UI**：工单上「确认订单」；摘要只读。  
- **效果**：`buyer_order_ack=true`；若供应已 ack → `ORDER_EFFECTIVE`。  
- **对话**：只报告「已写入确认」或「仍待供应确认」，**禁止**在 ack=false 时说已确认。

### G2. 供应确认（对端，不在 AB 组实现细节内，但 AB 必须消费）

- AB 只**订阅** `supplier_order_ack`；不替供应点确认。

### G3. 开启物流询价入口

- **前置**：`ORDER_EFFECTIVE`。  
- **UI**：「去和物流询价下单」（Gate，非 Ask）。  
- **效果**：Case → `LOGISTICS_HINT` / 打开物流会话意图；**不**自动 `place_logistics_order`。  
- **若前置不满足**：按钮禁用 + 文案写明缺哪边 ack（读库字段）。

---

## 6. A 与 B 的同构差异（仅策略，不改契约）

| | 采购商 A | 采购商 B |
|--|----------|----------|
| 人设 | 保定 · 高档座椅 | 承德 · 平价办公 |
| 默认物料 | 300kg / 高档面料倾向 | 200kg / 标准件倾向 |
| Ask A3 默认推荐 | 可更偏「议价/品质」 | 可更偏「直接下单/省钱」 |
| 状态机 / Ask / Gate | **同一套** | **同一套** |
| 数据 | `buyer-a.sqlite3` + 独立 Case 文件 | `buyer-b.*` 独立 |

---

## 7. Runtime 伪契约（实现时照此，勿再发明）

```text
on_user_message(m):
  snapshot = load_case_and_tickets()          # 唯一真相
  loop:
    thought = model(snapshot, m, tool_results)
    if thought.tool == AskUserQuestion:
      answers = UI.block_for_choices(thought.input)
      tool_results += answers
      continue
    if thought.tool == gate_confirm_order:
      deny  # 模型不能「调用确认」；确认只来自 UI Gate 事件
    if thought.tool in business_tools:
      tool_results += exec(tool)               # 写库
      snapshot = load_case_and_tickets()       # 强制重读
      continue
    speak(projection(snapshot, thought.say)) # 只投影
    break

on_gate_event(confirm_order | open_logistics, ticket_id):
  transition(...)                             # 写库
  # 可选：push 系统消息「状态已变更为 X」，再让模型读状态解说
```

**三条硬约束**

1. 每次工具写库后 **必须重新 load snapshot**。  
2. `speak` 前若话术与 snapshot 冲突 → 改话术或闭嘴，不许「智能体坚持」。  
3. Ask 挂起期间 **不得**并行改同一 Case 的互斥字段。

---

## 8. 最小可提交演示脚本（AB）

1. 人：「我打算买 500 套重型脚轮 300kg，请发现并报价」  
2. Gate：勾选供应 → 询价回价  
3. Ask：路径三选一（或二选一）→ 直接下单 A  
4. Gate：采购确认货单 →（供应侧确认）→ 界面显示 **ORDER_EFFECTIVE**  
5. Gate：「去询运」可点；未生效时灰掉并写明原因  

验收：**步骤 4 完成后，任意对话追问「确认了吗」必须答「已双方确认/已生效」，且询运 Gate 可点。**

---

## 9. 刻意不做（本阶段）

- 不在本设计里重做物流组 / 供应组内部；只定义 AB 对它们的**接口期望**（peer ack、询运入口）。  
- 不保留「对话里假装确认」。  
- 不把短名单、确认订单、路径选择做成同一种 choice-panel。

---

## 10. 下一步（仍设计，未开工）

1. 把旧 `hitl_policy` / `choice_actions` 对照本表打「废弃 / 迁移」标签。  
2. 画一张 AB 仅含的时序图（人 / Runtime / Case / Ticket）。  
3. 定工具清单最小集：`discover` / `confirm_shortlist` / `rfq` / `AskUser` / `decide` / `spawn_order` / `read_ticket`；Gate 为 HTTP 事件非工具。
