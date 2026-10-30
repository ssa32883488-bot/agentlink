# 演示视频分镜（3–5 分钟 MP4）

> 禁止出镜校名/LOGO/指导教师。画质优先特写协议证据。

| 段 | 时长 | 画面 | 旁白要点 |
|---|---|---|---|
| 0 片头 | 10s | 作品名「采联 AgentLink」+ 一句话：跨云多智能体采购互联 | 基于 AIP 国标与梧桐平台 |
| 1 拓扑 | 25s | 腾讯采购侧 / 阿里供应侧示意图 | 六智能体、mTLS、协议平面 |
| 2 注册 | 30s | 平台 ACS/AIC 列表或健康检查六端点 | 已完成平台注册 |
| 3 **ADP 发现特写** | 45s | 对话「开始采购并发现」；右侧显示 **平台** 徽章；必要时 `refresh` | 梧桐 ADP 自动发现，非本地伪造 |
| 4 **AIP 并行询价** | 50s | 确认三家→询价；协作时间线出现 Leader→供应A/B/C | 并行 AIP RPC |
| 5 **AMP 配对特写** | 50s | 展示同 taskId；messageId=`msg-{taskId}`；或平台访问量后台 | Access 双侧匹配计次 |
| 6 HITL | 30s | 对比三选/或演示一次 reject 作废 | 高风险人机门禁 |
| 7 收束 | 20s | 指标 KPI + 开源/标准化价值 | 必要验证场景已跑通 |

**录制前自检**
```bash
# buyer
/opt/agentlink/.venv/bin/python /opt/agentlink/scripts/demo_acps_evidence.py
# 期望：ACPS_EVIDENCE_PASS；docs/evidence/latest_pair.json
```
若发现为容灾：旁白必须说「本地 ACS 容灾补齐」，并再录一条纯平台命中镜头。
