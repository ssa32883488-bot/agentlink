# 采购智能体 A · V1 Tools Schema 草稿

> 配套：`design_procurement_dialogue_flow.md` §8  
> 状态：设计草稿（供实现/Wit capability 注册）；尚未全部落地代码  
> 约定：Tool **只返回结构化 JSON**；可交互表单由 UI 根据 `ui_hint` / 约定字段渲染

---

## 0. 公共类型

```jsonc
// PartnerRef：已发现或用户选中的对象
{
  "agent_id": "supplier-a",          // 本侧稳定短码，可选
  "aic": "1.2.156.3088.1....",       // 必填（平台身份）
  "name": "采联供应商智能体A",
  "endpoint": "https://39.105.20.113:8011/rpc",
  "skills": ["agentlink.supplier.quote"]
}

// LineItem：组合需求一行
{
  "sku": "part-a",                   // 或 material_code
  "name": "零件a",
  "qty": 100,
  "unit": "件",
  "specs": {}                        // 可选技术规格
}

// Money
{ "amount": 1000.0, "currency": "CNY" }

// ToolError（任出参可带）
{
  "ok": false,
  "error": {
    "code": "ADP_EMPTY|AIP_TIMEOUT|VALIDATION|HITL_REQUIRED|...",
    "message": "人可读说明"
  }
}
```

**案件上下文**：多数 Tool 隐式使用当前 `case_id`（会话绑定）；也可显式传入。

---

## 1. `discover.suppliers`

### 1.1 Description（capability 文案建议）

> 向梧桐 ADP 查找供应商智能体；本侧初筛后返回结构化候选并落库。结果供 UI 渲染勾选表单，不发起询价。平台无命中则候选为空。

### 1.2 Input

```json
{
  "type": "object",
  "required": [],
  "properties": {
    "case_id": { "type": "string", "description": "可选；空则用当前活跃案或先建案" },
    "query": {
      "type": "string",
      "description": "发现查询语，如「工业零件供应商 报价」；空则由 brief/行项目生成"
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10,
      "default": 5,
      "description": "初筛后最多保留几家（建议 ≤5，与 rfq 并行上限对齐）"
    },
    "refresh": {
      "type": "boolean",
      "default": false,
      "description": "true=绕过发现缓存，强制打平台"
    }
  }
}
```

### 1.3 Output

```json
{
  "type": "object",
  "required": ["ok", "case_id", "source", "candidates", "ui_hint"],
  "properties": {
    "ok": { "type": "boolean" },
    "case_id": { "type": "string" },
    "source": {
      "type": "string",
      "enum": ["platform_adp", "platform_adp_empty"]
    },
    "discovery_url": { "type": "string" },
    "elapsed_ms": { "type": "integer" },
    "platform_error": { "type": ["string", "null"] },
    "candidates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["candidate_id", "aic", "name", "endpoint"],
        "properties": {
          "candidate_id": { "type": "string", "description": "本案内稳定 id，供表单勾选回传" },
          "agent_id": { "type": "string" },
          "aic": { "type": "string" },
          "name": { "type": "string" },
          "endpoint": { "type": "string" },
          "skills": { "type": "array", "items": { "type": "string" } },
          "matched_skill": { "type": ["string", "null"] },
          "match_reason": { "type": "string", "description": "初筛理由，给人看" },
          "source_label": { "type": "string", "const": "平台发现" }
        }
      }
    },
    "ui_hint": {
      "type": "object",
      "description": "UI 契约：渲染多选表单",
      "properties": {
        "form": { "const": "shortlist_confirm" },
        "title": { "type": "string" },
        "min_select": { "type": "integer", "default": 1 },
        "max_select": { "type": "integer", "default": 5 },
        "submit_action": {
          "type": "string",
          "const": "rfq.send_batch",
          "description": "用户确认后建议触发的下一 Tool"
        }
      }
    },
    "hitl": {
      "type": "object",
      "properties": {
        "gate": { "const": "confirm_shortlist" },
        "prompt": { "type": "string" }
      }
    }
  }
}
```

### 1.4 UI 回传（人勾选后，非本 Tool 出参）

用户提交表单 → 对话或 API 带上：

```json
{
  "case_id": "case-xxx",
  "selected_candidate_ids": ["cand-1", "cand-2", "cand-3"]
}
```

Agent 据此调用 `rfq.send_batch`。

---

## 2. `rfq.send_batch`

### 2.1 Description

> 对用户已确认的短名单（1–5 家）并行发起初步询价；全部返回（或超时）后拼接为一次结果。期望各家回执含货价+运费（供应侧已含物流）。

### 2.2 Input

```json
{
  "type": "object",
  "required": ["selected"],
  "properties": {
    "case_id": { "type": "string" },
    "selected": {
      "type": "array",
      "minItems": 1,
      "maxItems": 5,
      "items": {
        "oneOf": [
          { "type": "string", "description": "candidate_id" },
          {
            "type": "object",
            "required": ["aic", "endpoint"],
            "properties": {
              "candidate_id": { "type": "string" },
              "agent_id": { "type": "string" },
              "aic": { "type": "string" },
              "endpoint": { "type": "string" },
              "name": { "type": "string" }
            }
          }
        ]
      }
    },
    "lines": {
      "type": "array",
      "description": "覆盖本案 brief 行项目；空则用 case 内已存需求",
      "items": { "$ref": "LineItem" }
    },
    "ship_to": {
      "type": "object",
      "properties": {
        "region": { "type": "string" },
        "city": { "type": "string" },
        "postal_code": { "type": "string" }
      }
    },
    "timeout_ms": {
      "type": "integer",
      "default": 60000,
      "description": "单家上限；batch 等齐或按策略截断"
    }
  }
}
```

### 2.3 Output

```json
{
  "type": "object",
  "required": ["ok", "case_id", "quotes", "summary"],
  "properties": {
    "ok": { "type": "boolean" },
    "case_id": { "type": "string" },
    "parallel": { "type": "integer", "minimum": 1, "maximum": 5 },
    "quotes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["partner", "status"],
        "properties": {
          "partner": { "$ref": "PartnerRef" },
          "status": {
            "type": "string",
            "enum": ["ok", "timeout", "error", "rejected"]
          },
          "error": { "type": "string" },
          "task_id": { "type": "string", "description": "AIP taskId，AMP 对账用" },
          "distance_km": { "type": ["number", "null"] },
          "lead_time_days": { "type": ["number", "null"] },
          "line_prices": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "sku": { "type": "string" },
                "qty": { "type": "number" },
                "unit_price": { "type": "number" },
                "line_total": { "type": "number" }
              }
            }
          },
          "goods_total": { "type": "number" },
          "freight": {
            "type": "object",
            "description": "供应商侧带回的运费（其被动询物流结果）",
            "properties": {
              "amount": { "type": "number" },
              "currency": { "type": "string" },
              "note": { "type": "string" }
            }
          },
          "grand_total": { "type": "number", "description": "货+运" },
          "currency": { "type": "string", "default": "CNY" },
          "raw_policy_hints": {
            "type": "array",
            "items": { "type": "string" },
            "description": "可选；首轮可能尚未给折扣门槛"
          }
        }
      }
    },
    "summary": {
      "type": "object",
      "properties": {
        "ok_count": { "type": "integer" },
        "fail_count": { "type": "integer" },
        "lowest_grand_total": { "type": ["number", "null"] },
        "lowest_partner_aic": { "type": ["string", "null"] }
      }
    },
    "ui_hint": {
      "type": "object",
      "properties": {
        "view": { "const": "quote_compare_table" }
      }
    },
    "hitl": {
      "type": "object",
      "properties": {
        "gate": { "const": "after_initial_quotes" },
        "prompt": { "type": "string", "examples": ["目前报价可以，尝试去谈谈折扣和优惠"] }
      }
    }
  }
}
```

---

## 3. `partner.dialog`

### 3.1 Description

> 与已筛选供应商进行单轮 AIP 业务对话。用于议价、改量问价、澄清等；不替代首轮并行询价（用 rfq.send_batch）。

### 3.2 Input

```json
{
  "type": "object",
  "required": ["partner", "intent"],
  "properties": {
    "case_id": { "type": "string" },
    "partner": {
      "oneOf": [
        { "type": "string", "description": "candidate_id 或 agent_id" },
        { "$ref": "PartnerRef" }
      ]
    },
    "intent": {
      "type": "string",
      "enum": ["negotiate", "clarify", "requote", "initial_quote"],
      "description": "initial_quote 仅用于补询单家；多家首轮请用 rfq.send_batch"
    },
    "goal_text": {
      "type": "string",
      "description": "议价/问价自然语言目标，禁止塞入内部预算数字"
    },
    "lines": {
      "type": "array",
      "items": { "$ref": "LineItem" },
      "description": "改量时传入新行项目"
    },
    "message": {
      "type": "string",
      "description": "可选补充话术；默认由 intent+goal 生成合规请求"
    },
    "timeout_ms": { "type": "integer", "default": 60000 }
  }
}
```

### 3.3 Output

```json
{
  "type": "object",
  "required": ["ok", "case_id", "partner", "intent", "result"],
  "properties": {
    "ok": { "type": "boolean" },
    "case_id": { "type": "string" },
    "partner": { "$ref": "PartnerRef" },
    "intent": { "type": "string" },
    "task_id": { "type": "string" },
    "result": {
      "type": "object",
      "description": "与 rfq 单条 quote 对齐的结构化回执 + 可选政策",
      "properties": {
        "status": { "type": "string" },
        "goods_total": { "type": "number" },
        "freight": { "type": "object" },
        "grand_total": { "type": "number" },
        "line_prices": { "type": "array" },
        "applied_qty": {
          "type": "array",
          "description": "若因折扣门槛加量，回写实际成交数量假设",
          "items": { "$ref": "LineItem" }
        },
        "policy": {
          "type": "object",
          "description": "可选结构化政策，供 calc 使用",
          "properties": {
            "type": {
              "type": "string",
              "enum": ["qty_discount", "free_shipping", "full_reduction", "other"]
            },
            "description": { "type": "string" },
            "threshold": { "type": "object" }
          }
        },
        "note": { "type": "string" }
      }
    }
  }
}
```

---

## 4. 本地业务类

### 4.1 `erp.query_inventory`

**Input**：`{}` 或 `{ "low_only": false }`  
**Output**：

```json
{
  "ok": true,
  "items": [
    {
      "code": "GAS-ROD",
      "name": "气压棒",
      "available": 25,
      "safety_stock": 60,
      "unit": "件",
      "low": true,
      "preferred_supplier": "supplier-a"
    }
  ],
  "low_count": 6
}
```

### 4.2 `erp.query_orders`

**Input**：`{ "kind": "sales|purchase|all", "limit": 20, "case_id": null }`  
**Output**：`{ "ok": true, "items": [ /* 订单摘要 */ ] }`

### 4.3 `erp.query_notifications`

**Input**：`{ "unread_only": false, "limit": 20 }`  
**Output**：`{ "ok": true, "items": [...], "unread": 0 }`

### 4.4 `erp.query_db`（可选、受控）

**Input**：`{ "resource": "inventory|sales_orders|...", "filter": {}, "limit": 50 }`  
**约束**：仅表白名单；禁止原始 SQL 字符串入参。  
**Output**：`{ "ok": true, "resource": "...", "rows": [] }`

---

## 5. 记忆类

存储键建议：`case_id` + `session_id`；值为 JSON 文档。

### 5.1 `memory.inject`

**Input**：

```json
{
  "case_id": "case-xxx",
  "entries": [
    {
      "key": "ship_to",
      "value": { "city": "保定" },
      "ttl_sec": null,
      "tags": ["constraint"]
    }
  ]
}
```

**Output**：`{ "ok": true, "written": 1 }`

### 5.2 `memory.extract`

**Input**：`{ "case_id": "...", "keys": ["ship_to", "selected_shortlist"], "tags": [] }`  
**Output**：`{ "ok": true, "entries": { "ship_to": { ... } } }`

### 5.3 `memory.record`

**Input**：

```json
{
  "case_id": "...",
  "event": "shortlist_confirmed|quotes_received|scheme_selected|...",
  "payload": {},
  "ref_ids": ["task-...", "cand-..."]
}
```

**Output**：`{ "ok": true, "record_id": "mem-..." }`

---

## 6. 计算类（可对模型暴露）

### 6.1 `calc.compare_table`

**Input**：`{ "case_id": "...", "quote_set": "latest|after_negotiate" }`  
**Output**：行=供应商，列=距离/交期/货价/运费/总价/备注；供 UI 表。

### 6.2 `plan.propose`

**Input**：`{ "case_id": "...", "modes": ["S1", "S2"] }`（V1 不含采购侧 S3 统调）  
**Output**：方案列表（总价、组成、风险说明）。

---

## 7. 与现有实现映射 / 废弃

| 目标 Tool | 现有近似 | 动作 |
|---|---|---|
| `discover.suppliers` | `flow.discover` | **重命名+加强**：出 `candidate_id`、`ui_hint`；已无本地 ACS |
| `rfq.send_batch` | `flow.confirm_shortlist_and_rfq` | **拆确认与询价**：确认在 UI HITL；本 Tool 只并行询价 1–5；回执扩展 freight |
| `partner.dialog` | `flow.decide_negotiate` 等碎片 | **新建统一接口**；议价走 intent=negotiate |
| `erp.query_inventory` | 同名 | 保留，补 description |
| `erp.query_orders` | `erp.query_sales_orders` | 扩展 kind |
| `erp.query_notifications` | 同名 | 保留 |
| `memory.*` | 无（仅 `_ACTIVE_CASE_ID`） | **新建** |
| `calc.*` / `plan.propose` | `compare_quotes` 内嵌 | 抽出可调 Tool |
| `flow.shipping_contract`（采购呼物流） | 有 | **V1 采购侧停用/降级**（物流在供应侧） |
| `flow.decide_auction` | 有 | V1 可选保留，非本图主路径 |
| `discover.logistics`（采购） | 无 | **不装** |

---

## 8. 实现顺序建议

1. Schema 落地为 Pydantic / capability 参数注解  
2. `discover.suppliers` 输出对齐 + UI `shortlist_confirm` 表单  
3. `rfq.send_batch`（1–5 并行，货+运字段；供应侧后补被动物流）  
4. `partner.dialog`  
5. `memory.*` + 案件绑定  
6. `calc.compare_table` / `plan.propose`  
7. 供应侧 `discover.logistics` 被动技能（并行轨道）

---

## 9. 修订

| 日期 | 说明 |
|---|---|
| 2026-10-26 | Schema 草稿首版 |
