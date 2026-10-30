# 竞价链路时延优化 · 实测

## 优化前（基线）

| 项 | 值 |
|----|----|
| 组群 invite | 串行；跨云单家常超时 10–30s+ |
| 盲拍等待 | 默认 45s |
| 空榜后 | 再串行 RPC |
| 观测墙钟 | 常 >30–120s |

```json
{
  "note": "优化前（同场景 S2 / 历史观测）",
  "group_invite": "串行；单家跨云 ReadTimeout 常 10–30s+，整场叠加",
  "group_bid_wait_sec": 45,
  "empty_group_then_rpc": "空等收齐后再串行 RPC",
  "auction_wall_observed": "常 >30–120s（含超时），S2 finish 全链路曾至数分钟",
  "rpc_mode": "for-loop 串行 aip_start_structured"
}
```

## 优化后（本次）

| 项 | 值 |
|----|----|
| case | `case-ad47a401` |
| ok (priced≥2) | `True` |
| transport | `rpc` |
| early_abort | `True` / `insufficient_joined_suppliers` |
| discover_ms | 16112.1 |
| rfq_ms | 7444.4 |
| **auction_wall_ms** | **7632.6** |
| timings_ms | `{"group_ms": 7261.1, "group_invite_ms": 5003.1, "group_early_abort": true, "group_abort_reason": "insufficient_joined_suppliers", "rpc_parallel_ms": 311.1, "rpc_parallel_n": 2, "auction_total_ms": 7574.9, "priced": 2}` |
| priced | 2 |
| bids | `[{"supplier_agent_id": "supplier-a", "unit_price": 13.5, "transport": "rpc", "error": null}, {"supplier_agent_id": "supplier-c", "unit_price": 15.0, "transport": "rpc", "error": null}]` |

## 变化说明

1. **并行 invite**：墙钟≈最慢一家，不再累加。
2. **入组不足早停**：避免 45s 空等，立刻并行 RPC。
3. **并行 RPC 盲拍**：N 家墙钟≈max(单家)。
4. **可观测**：`auction_summary.timings_ms` 写入案例。

## 如何复现

```text
py -3 scripts/_deploy_latency_opt.py
py -3 scripts/_bench_auction_latency.py
```
