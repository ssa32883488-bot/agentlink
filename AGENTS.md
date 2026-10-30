# 采联 AgentLink — 仓级 Agent 宪法索引

> 对齐：`入职向AI应用开发训练/Agent教程` + DOC-AI V2.0  
> 原则：机器可读、行为性规范、渐进披露。本文件是**仓级索引**，各主体细则见 `agents/*/AGENTS.md`。

## 项目目标

在 ACPs（梧桐）上实现跨企业采购协同：询价 → 报价 → 比较 → 物流 → 订单草案 →（人工）激活。

## 非目标

- 不做链上结算 / 跨主体托管资金  
- 不做无审批的自动成交  
- 不把六个经营主体合并成一个“全能 Agent”进程  

## 技术栈硬约束

| 层 | 选型 |
| --- | --- |
| 跨主体协议 | ACPs AIC/ACS/ADP/AIP/AMP，acps-sdk ≥ 2.2.0 |
| 认知编排 | LangGraph StateGraph + Checkpointer |
| 工具/模型 | LangChain Tools；LLM 可替换 |
| 副作用 | **仅**经 `ToolGateway` |
| 发现 | ACS 可发现为硬门槛；本地优先，再平台注册 |

## 架构约束（禁止项）

1. 禁止 LLM / Graph 节点直接写库、发单、扣库存  
2. 禁止跨供应商共享 Working Memory / Scratchpad  
3. 禁止把业务字段伪装成 AIP 原生 type；业务走 `StructuredDataItem`  
4. 禁止超时自动 `activate_order`  
5. 禁止模型改写 Policy / Constitution  

## 权限模型

`suggest` → `negotiate` → `commit`。critical 工具必须 `commit` + HITL。

## Sub Agents（独立进程）

| Agent | 目录 | 角色 |
| --- | --- | --- |
| 采购 A | `agents/buyer_a` | 询价发起、比较、草案 |
| 采购 B | `agents/buyer_b` | 标准品快速采购 |
| 供应商 A | `agents/supplier_a` | 标准品报价 |
| 供应商 B | `agents/supplier_b` | 定制/MOQ |
| 供应商 C | `agents/supplier_c` | 库存紧张/替代 |
| 物流 | `agents/logistics` | 运费与时效 |

跨企业协作：去中心化（AIP）。采购侧对内可轻量 Supervisor 编排本侧 Tools/Skills。

## 共享运行时

见 `agentlink_runtime/` 与 DOC-AI：Context Manager、ToolGateway、Memory、Audit。

## 输出契约

对外业务一律：`schema_type` + `schema_version` + `business_id` + `payload`。

## 变更

工具/Skill/Policy 变更需评审；熵治理禁止模型直接改生产工具定义。
