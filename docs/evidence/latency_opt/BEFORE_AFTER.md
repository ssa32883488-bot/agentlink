# 竞价链路时延优化 · 前后对比

**日期**：2026-10-30  
**范围**：组群 invite / 盲拍等待 / RPC 回退（协议平面，不含 LLM）  
**代码**：`commerce/group_mq.py` · `commerce/flow_service.py`  
**部署**：腾讯云 buyer-a（`scripts/_deploy_latency_opt.py`）  
**实测**：`docs/evidence/latency_opt/bench_20261030_043713/`

---

## 1. 优化了什么

| # | 改动 | 机制 |
|---|------|------|
| 1 | **并行 invite** | `asyncio.gather` 同时邀请短名单+物流；单家 `ACPS_GROUP_INVITE_TIMEOUT_SEC=5` |
| 2 | **入组不足早停** | `joined` 供应 &lt; `ACPS_GROUP_MIN_SUPPLIERS=2` 时立即空榜返回，不再空等盲拍 |
| 3 | **缩短盲拍等待** | 默认 `ACPS_GROUP_BID_WAIT_SEC=12`（原硬编码等待上限 45s） |
| 4 | **并行 RPC 盲拍** | 回退路径 `asyncio.gather` 对 N 家 `aip_start_structured`（对齐 RFQ） |
| 5 | **可观测** | `auction_summary.timings_ms`：`group_ms` / `invite_ms` / `rpc_parallel_ms` / `auction_total_ms` |

环境变量（已写入线上 `/opt/agentlink/.env`）：

```text
ACPS_GROUP_INVITE_TIMEOUT_SEC=5
ACPS_GROUP_MIN_SUPPLIERS=2
ACPS_GROUP_BID_WAIT_SEC=12
```

---

## 2. 前后对比（同场景：RM-CASTER-200 · A+C）

| 指标 | 优化前 | 优化后（实测） | 变化 |
|------|--------|----------------|------|
| 组群 invite | **串行**；单家跨云 ReadTimeout 常 10–30s+，N 家累加 | **并行**；墙钟≈最慢一家，上限约 **5s** | 由 O(Σ) → O(max) |
| 入组失败后 | 仍进入盲拍等待，常空等到 **~45s** 再回退 | **早停**（`insufficient_joined_suppliers`），约 **5s** 内切 RPC | 去掉空等 |
| RPC 盲拍 | **串行** for-loop | **并行** gather | 2 家实测 **311 ms** |
| 竞价段墙钟 `auction_wall_ms` | 观测常 **>30–120 s**（超时+串行回退） | **7633 ms（≈7.6 s）** | 约 **4–15×** |
| 有效出价 | 依赖回退才 ≥2 | **priced=2**（A@13.5 / C@15.0） | 正确性保持 |
| transport | 多为 rpc 回退 | rpc + `early_abort=true` + `rpc_parallel=true` | 路径可解释 |

### 本次实测拆解（`case-ad47a401`）

```text
group_ms            7261   ← 并行 invite(~5003) + 早停，未空等 45s
rpc_parallel_ms      311   ← 2 家并行盲拍
auction_total_ms    7575
auction_wall_ms     7633
priced                 2
```

对照历史体感：同场景 S2 全链路曾因串行 invite 超时堆栈拖到 **数分钟**；仅竞价段即可从「分钟级风险」收到「约 8 秒内出榜」。

---

## 3. 如何优化（设计意图）

```
优化前:
  invite(A) ──timeout──► invite(C) ──timeout──► invite(物流)
       └──────── 串行累加 ────────┘
  → 盲拍 wait≤45s（常 0 出价）→ RPC(A) → RPC(C)  再串行
  墙钟 ≈ Σ(invite) + wait + Σ(rpc)

优化后:
  invite(A)╗
  invite(C)╠══ max≤5s ══╗
  invite(L)╝            ║
                        ▼
              joined供应 < 2 ? ──yes──► 立即并行 RPC(A,C)
                        │                  └─ wall ≈ max(rpc)≈0.3s
                        no
                        ▼
              盲拍 wait≤12s → 收齐/超时 →（可选 TCO）
```

协议语义未改：仍是 Group 优先、失败/空榜回退 AIP；只改调度与超时策略。

---

## 4. 未改 / 仍慢的部分

| 项 | 本次实测 | 说明 |
|----|----------|------|
| ADP 发现 | discover_ms ≈ **16.1 s**（缓存未强制刷新路径仍偏慢） | 不在本轮；需缓存命中率与平台侧优化 |
| RFQ | rfq_ms ≈ **7.4 s** | 已并行；跨云 AIP 热路径仍有空间 |
| LLM 对话 | 未计入本 bench | 体验层另报；协议 KPI 勿与模型时延混写 |

---

## 5. 复现命令

```text
py -3 scripts/_deploy_latency_opt.py
py -3 scripts/_bench_auction_latency.py
```

证据目录：`docs/evidence/latency_opt/bench_*/result.json` + `REVIEW.md`
