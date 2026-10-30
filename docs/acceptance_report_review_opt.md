# 采联 AgentLink｜DeepSeek 审查后线上优化验收报告

> 日期：2026-10-26  
> 范围：编排层 / UI / 文案 / 埋点（**未改** AIP/ADP/AMP 报文结构与梧桐接入方式）  
> 对照：`docs/deepseek_third_party_review.md` D1–D8

---

## 1. 结论

| 项 | 状态 |
|---|---|
| 线上代码优化（D2–D7） | **已上线**（buyer `81.70.46.119`，UI `:8090`，buyer-a `:8010`） |
| 烟雾验收 | **通过**（`HITL_SMOKE_PASS`） |
| 材料包（D1）/ 答辩话术（D8） | **未在本轮代码交付**，仍为冲奖 P0 |

---

## 2. 已落地项对照

| 编号 | 内容 | 实现要点 | 验收 |
|---|---|---|---|
| **D2** | HITL 四态 + 幂等 | `commerce/hitl_gate.py`；`POST /api/flow/cases/{id}/hitl`（approve/edit/reject/respond）；reject → `EXCEPTION`+`voided`，阻断短名单/询价；同 shortlist 指纹询价幂等（`rfq_fingerprint`） | reject 后 confirm-shortlist 返回 **400**；同 ids 二次 confirm 幂等 |
| **D3** | 协作叙事 + 下一步引导 | Wit `INSTRUCTIONS` 强制【步骤 x/10】+ 角色动作 + 下一步；工具返回 `narrative` / `hitl.next_hint` | Prompt 与 status 文案层已部署 |
| **D4** | 轨迹每跳命名 | 协作面板：角色 · 动作名 · 状态 · 耗时 · task 短码 | UI `app.js` / `styles.css` 已部署 |
| **D5** | 容灾显式化 | 候选 `source_label` / `degrade`；发现 meta 带 `degrade_reason`；界面徽章「平台 / 容灾」 | 发现完成日志与右侧面板可见 |
| **D6** | 发现短 TTL 缓存 | `ADP_DISCOVER_CACHE_TTL` 默认 60s；缓存命中跳过重复平台检索 | 代码已上线 |
| **D7** | 成效只读数据 | `GET /api/flow/metrics` + 右侧 KPI 条（AMP 访问/消息/任务/成功率） | 烟雾：`kpi.success_rate_pct=100.0`（按 2xx/awaiting-* 计） |
| **D1** | 材料包 | 后台截图 / 技术方案 PDF / 视频 / PPT | **待人工** |
| **D8** | 创新性叙事 | 跨云双侧 AMP 对账 + HITL 门禁答辩话术 | **待答辩稿** |

---

## 3. 部署与烟雾记录

- 部署脚本：`scripts/_deploy_review_opt.py` → `/opt/agentlink/`，已重启 `agentlink-buyer-a`、`agentlink-ui-buyer`
- 烟雾脚本：`scripts/_smoke_hitl_opt.py`
  - `reject_blocks_ok 400`
  - `idempotent_shortlist_ok`
  - `HITL_SMOKE_PASS`
- UI：`https://81.70.46.119:8090/`（服务 active）

---

## 4. 新增/变更文件

| 路径 | 说明 |
|---|---|
| `commerce/hitl_gate.py` | 门禁元数据与四态决策常量 |
| `commerce/amp_metrics.py` | AMP 本地日志 KPI 汇总 |
| `commerce/discovery.py` | TTL 缓存 + 容灾标注 |
| `commerce/flow_service.py` | HITL decide、询价幂等、叙事 hitl |
| `commerce/flow_routes.py` | `/hitl`、`/metrics` |
| `commerce/chat_buyer_wit.py` | 协作叙事 Prompt + `flow.hitl_decide` |
| `ui/static/app.js` / `styles.css` | 时间线、徽章、KPI 条 |

---

## 5. 演示话术（对接 D5/D8）

1. **平台命中**：右侧显示「平台 · platform_adp…」  
2. **若走容灾**：明确说「平台超时/未齐 → 本地 ACS 容灾补齐」，徽章为黄色「容灾」——这是设计，不是造假。  
3. **HITL**：对话说「拒绝」→ 案件作废，不可再询价；再说「确认三家并询价」走 approve 路径。  
4. **AMP**：同 taskId 双侧配对；KPI 条可截图进材料。

---

## 6. 剩余冲奖清单（非代码）

1. 梧桐后台 **访问量截图**（硬门槛）  
2. 技术方案 PDF（架构 + 协议时序 + 跨云拓扑）  
3. 3 分钟视频：ADP 发现特写、AIP 并行询价、AMP 同 taskId 特写  
4. 答辩 PPT：用「双侧 AMP 对账 + HITL 四态门禁」讲清二次开发差异  

补齐后预估可从约 **60–66** 再抬 **+8~12**（见第三方审查）。
