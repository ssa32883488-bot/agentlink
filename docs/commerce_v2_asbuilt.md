# commerce_v2 技术现状（As-Built）

> 更新日期：2026-10-30  
> 范围：双云部署下的 `AGENTLINK_RUNTIME=v2` 采购双路径（普通询价 / 组群竞价）  
> 需求底稿：[`design_two_paths_interconnect.md`](./design_two_paths_interconnect.md)  
> 交互契约：[`../commerce_v2/interaction_contract.md`](../commerce_v2/interaction_contract.md)

---

## 1. 一句话

采购对话主路径已切到 **commerce_v2 确定性编排**（非 Wit 主路径）：梧桐 ADP 发现 → 人确认短名单 → 点对点询价/议价，或采购主持开群走国标 Group；**多品需求按行全覆盖**，组群汇总须覆盖全部品类后再拆单/下单。

---

## 2. 运行时与部署

| 项 | 现状 |
|----|------|
| 开关 | `AGENTLINK_RUNTIME=v2`（buyer / supplier / logistics） |
| 采购 UI | `https://ashui.online:8090/`（buyer-a 单智能体控制台） |
| 腾讯云 | buyer-a `8010` · buyer-b `8012` · logistics `8015` |
| 阿里云 | supplier-a/b/c `8011/8013/8014` |
| 旧 Wit/flow | `commerce/_legacy/`；组群 MQ 实现 `commerce/_legacy/group_mq.py` |
| 主包 | `commerce_v2/`（routes · chat_api · buyer_path_* · group_room · partner_*） |

---

## 3. 两条业务路径（已落地）

### 3.1 普通询价（点对点）

```
改写(+多品 items) → ADP 发现(多 SKU 并集) → SHORTLIST_PENDING
       → 人「确认并询价」→ 初报 → BARGAIN_ASK → 买法/下单 → 工单 Gate
```

关键模块：`buyer_path_normal.py` · `protocol_bridge.discover_suppliers_for_brief` · `partner_supplier`

### 3.2 组群竞价（采购主持 · 共同上下文）

```
改写 → 发现 → 人发「我要组群竞价」→ GROUP_ASK（勾选供应±物流）
       → 确认开群 → 国标 Group MQ(优先) / 本地续跑
       → 按行 group_bid → 物流方案 → GROUP_DECIDE 全量覆盖方案
       → 拆单 place_order=on → 系列工单
```

关键模块：`buyer_path_group.py` · `group_room.py` · `group_mq.py`  
UI：置顶「组群竞价聊天室」模态（可收起；收起后轮询不强弹）

---

## 4. 本轮关键能力（2026-10-30 晚）

### 4.1 多品需求不漏项

| 问题 | 修复 |
|------|------|
| 「脚轮+坐垫」被 `llm_guard_rebind` 当成脚轮幻觉丢掉 | 仅当用户**未提**脚轮却改写成脚轮时拦截 |
| 改写/询价只认单 SKU | 新增 `demand_items.py`：拆行 `items[]`，`enrich_brief_items` |
| 发现只召回坐垫厂 | `discover_suppliers_for_brief` 按全部 SKU **并集**召回 |
| 组群只报一种货 | 按供应目录能力 **按行** `v2.group_bid`；汇总主推「全量覆盖」拆单 |

### 4.2 组群国标通道

| 问题 | 修复 |
|------|------|
| 证书根路径错误 / AIC 过短 | 证书路径 `parents[2]`；AIC 用证书 CN 写入 `.env` |
| 邀请供应 HTTPS 自签失败 | `AIP_SSL_INSECURE` + invite `verify=False` |
| 开群后 AIP 卡住空消息 | 超时 / `force_local` / 「继续组群报价汇总」续跑 |

### 4.3 下单与物流工单

- 供应商工具 `place_order`：**仅**用户明确下单且信封带 `place_order=on` 才落单  
- 物流确认闸使用 **logistics ticket id**（不再误用 order_id）  
- 对话历史 / `hitl_pending=null` 500 已兜底

### 4.4 UI

- 组群「收起」：写入 `groupRoomCollapsed`，4s 轮询只刷新不重开；提供「展开组群聊天室」  
- GROUP_ASK 保留「确认组群竞价」按钮，避免无处可点

---

## 5. 关键代码地图

| 能力 | 路径 |
|------|------|
| 多品拆行 | `commerce_v2/demand_items.py` |
| 需求改写 | `commerce_v2/llm_rewrite.py` |
| 发现并集 | `commerce_v2/protocol_bridge.py` |
| 普通路径 | `commerce_v2/buyer_path_normal.py` |
| 组群路径 | `commerce_v2/buyer_path_group.py` |
| 聊天室/汇总 | `commerce_v2/group_room.py` |
| 供应工具 | `commerce_v2/partner_supplier.py` · `supplier_tools.py` |
| Group MQ | `commerce/_legacy/group_mq.py` |
| 前端聊天室 | `ui/static/app.js` · `index.html` · `styles.css` |

---

## 6. 验收证据（最新）

| 类型 | 位置 |
|------|------|
| 浏览器双路径截图+日志 | [`evidence/verify_ui_shots/v2_dual_20261030_194944/`](./evidence/verify_ui_shots/v2_dual_20261030_194944/) |
| Word 报告 | 同目录 `commerce_v2_双路径询价全流程_20261030_194944.docx` |
| 索引 | [`evidence/verify_ui_shots/INDEX.md`](./evidence/verify_ui_shots/INDEX.md) |
| 双云冒烟 | [`evidence/v2_interaction_shots/REMOTE_ACCEPT_20261030.md`](./evidence/v2_interaction_shots/REMOTE_ACCEPT_20261030.md) |

实测要点（截图 run `20261030_194944`）：

- 普通：`case-e9d68c39` → `SHORTLIST_PENDING` → 确认询价 → `BARGAIN_ASK`；改写保留脚轮+坐垫  
- 组群：`case-0789948b` → `GROUP_ASK` → `GROUP_DECIDE`；`transport=group` · `grp-e8ce0890d8`；供应 A/B/C + 物流均 quoted；方案含「全量覆盖 · 2 品拆单」

复跑截图：

```powershell
.\.venv\Scripts\python.exe scripts\_capture_v2_dual_inquiry_shots.py
```

---

## 7. 已知限制 / 后续

1. 组群需求行数量偶发被库存/额定值串扰（日志曾出现「脚轮×300 / 坐垫×500」对不上用户「500/400」）——应强制以用户原话 qty 为准。  
2. 普通路径多品初报表格偶发把坐垫 qty 显示成与脚轮同量——展示层需按 `items[]` 分行。  
3. 公网 AIP `initial_quote` 偶发 failed 但本地智力仍有报价——需区分通道失败与业务回退展示。  
4. 组群选方案后到系列工单 ACTIVE 的 UI 全程截图可再补一轮。

---

## 8. 环境要点（组群）

```
AGENTLINK_RUNTIME=v2
V2_TRY_GROUP_MQ=1
ACPS_GROUP_IDENTITY_BINDING=1
AIP_SSL_INSECURE=1
BUYER_*_AIC / SUPPLIER_*_AIC / LOGISTICS_AIC = 证书 CN
```
