# 隔夜迭代结果（比赛协议基准）· 明日晨读

> 截止：2026-10-26 线上验收  
> 原则：**绝对以梧桐 ACPs 必要验证为生死线**（注册→发现→互联→访问），材料与叙事服务证据，不改协议报文结构。

---

## 一句话结论

**协议链路可证（午间已升级）**：ADP `platform_adp`，**A/B/C 三家均为平台发现**（见 `docs/continue_iteration_report.md`）；AIP 询价 3 报价；AMP 买卖双侧 **3/3 taskId 对账通过**（`AMP_BILATERAL_PASS`）。  
**仍卡冲奖/硬材料**：后台访问量截图 + 技术方案 PDF + 视频 + 答辩 PPT（草稿已备齐，待你转正/录制）。

---

## 今夜已完成

### A. 线上加固（已部署双云）

| 项 | 结果 |
|---|---|
| HITL 四态 + reject 作废 + 询价幂等 | 已上线 |
| 发现 `refresh` 绕过缓存 | `POST .../discover {"refresh":true}` |
| 容灾徽章 / source_label | A/B=`平台发现`，C=`本地容灾` |
| 协作面板按 `case_id` 过滤 | 已上线 |
| AMP Message operationName | receive Start → `aip.TaskCommand` |
| 供应侧 AMP Kafka | `.env` 已有 `AMP_KAFKA_*`，服务 active |
| 证据脚本 | `scripts/demo_acps_evidence.py` → **`ACPS_EVIDENCE_PASS`** |

### B. 最新硬证据（`docs/evidence/latest_pair.json`）

- case：`case-e9435f63`
- 发现：`platform_adp+local_fill`，`cache_hit=false`，`elapsed_ms≈27807`
- discovery_url：`.../acps-adp-v2/discover`
- RFQ：`COMPARE_PENDING`，**quotes=3**，errors=[]
- AMP buyer：`amp_message_send_count=3`，`messageId_equals_msg_taskId=true`
- 供应侧尾部可见 `eventType=receive` + `msg-task-…` + `aip.TaskCommand`

### C. 材料草稿（转正式件即可）

| 文件 | 用途 |
|---|---|
| `docs/materials/技术方案_附件2大纲稿.md` | 附件2 → PDF |
| `docs/materials/演示视频分镜脚本_3to5min.md` | 3–5 分钟录制 |
| `docs/materials/答辩PPT大纲_无校名.md` | 答辩（禁校名） |
| `docs/acceptance_report_review_opt.md` | 上一轮优化验收 |
| `docs/deepseek_third_party_review.md` | 第三方评分预估 |

---

## 明日你必须亲手做的（P0，否则必要验证翻车）

1. **登录梧桐后台截访问量**（含时间戳）→ 进佐证 PDF；命名建议 `YYYYMMDD-平台访问量.png`  
2. 技术方案 MD → **PDF≤10M**  
3. 按分镜录 **MP4 3–5 分钟**：特写 ADP 平台徽章、AIP 三家、AMP 同 taskId  
4. 答辩 PPT → PDF，**无校名/无导师**  
5. 若评委盯供应商 C：话术固定为「平台部分命中 + 本地 ACS 容灾补齐（设计）」；有余力再把 C 也推到平台可发现

---

## 演示入口

- UI：`https://81.70.46.119:8090/`（或 `https://ashui.online:8090/`）  
- 对话：「开始采购并发现供应商」→「确认三家并询价」→ 看右侧时间线与发现徽章  
- 复跑证据：SSH buyer 后  
  `/opt/agentlink/.venv/bin/python /opt/agentlink/scripts/demo_acps_evidence.py`

---

## 评分位势（对照 DeepSeek 审查）

| 维度 | 昨夜后变化 |
|---|---|
| 必要验证（生死线） | 技术侧证据加强；**截图仍缺** |
| AI 技术应用 | ADP/AIP/AMP 可演示稳定性↑ |
| 创新性 | 叙事稿已写「双侧 AMP + HITL」；靠答辩落地 |
| 项目实施/总结 | 依赖 PDF/视频是否交齐 |

预估：材料交齐前仍约 **60–66**；交齐并突出 AMP 特写可冲 **70+**。

---

## 工程索引

- 部署：`scripts/_deploy_overnight.py`  
- 证据：`scripts/demo_acps_evidence.py`  
- HITL 烟雾：`scripts/_smoke_hitl_opt.py`
