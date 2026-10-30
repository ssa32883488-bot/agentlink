# -*- coding: utf-8 -*-
"""Benchmark S2 auction wall-clock after latency opts; write evidence JSON/MD."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
OUT = (
    ROOT
    / "docs"
    / "evidence"
    / "latency_opt"
    / f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT.mkdir(parents=True, exist_ok=True)

REMOTE = r'''
set -a; . /opt/agentlink/.env; . /etc/agentlink/buyer-a.env; set +a
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, time, sys
sys.path.insert(0,"/opt/agentlink")
from commerce import flow_service as fs

async def main():
    t0=time.perf_counter()
    case=fs.create_from_brief(
        product_name="标准脚轮200kg", quantity=500, note="bench-latency-opt",
        lines=[{"sku":"RM-CASTER-200","name":"标准脚轮200kg","qty":500}],
    )
    cid=case["case_id"]
    t_disc0=time.perf_counter()
    case=await fs.step_discover(cid,"标准脚轮200kg", bypass_cache=False)
    disc_ms=round((time.perf_counter()-t_disc0)*1000,1)
    case=fs.step_confirm_shortlist(cid, ["supplier-a","supplier-c"])
    t_rfq0=time.perf_counter()
    case=await fs.step_rfq(cid)
    rfq_ms=round((time.perf_counter()-t_rfq0)*1000,1)
    case=fs.step_decide(cid,"auction")
    t_auc0=time.perf_counter()
    case=await fs.step_auction(cid)
    auc_wall_ms=round((time.perf_counter()-t_auc0)*1000,1)
    summary=case.get("auction_summary") or {}
    priced=[b for b in (case.get("auction_bids") or []) if b.get("unit_price") is not None]
    out={
        "case_id": cid,
        "ok": len(priced)>=2 and case.get("state")=="BID_REVIEW",
        "state": case.get("state"),
        "discover_ms": disc_ms,
        "rfq_ms": rfq_ms,
        "auction_wall_ms": auc_wall_ms,
        "auction_timings_ms": summary.get("timings_ms"),
        "transport": summary.get("transport"),
        "early_abort": summary.get("early_abort"),
        "abort_reason": summary.get("abort_reason"),
        "rpc_parallel": summary.get("rpc_parallel"),
        "priced": len(priced),
        "bids":[{"supplier_agent_id":b.get("supplier_agent_id"),"unit_price":b.get("unit_price"),"transport":b.get("transport"),"error":b.get("error")} for b in (case.get("auction_bids") or [])],
        "total_ms": round((time.perf_counter()-t0)*1000,1),
    }
    print("BENCH_JSON "+json.dumps(out,ensure_ascii=False), flush=True)

asyncio.run(main())
PY
'''


def main() -> None:
    print("OUT", OUT, flush=True)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    t0 = time.perf_counter()
    _, o, e = c.exec_command(REMOTE, timeout=360, get_pty=True)
    raw = (o.read() + e.read()).decode("utf-8", "replace")
    wall = round((time.perf_counter() - t0) * 1000.0, 1)
    c.close()
    (OUT / "remote.log").write_text(raw, encoding="utf-8")
    payload = None
    for line in raw.splitlines():
        if line.startswith("BENCH_JSON "):
            payload = json.loads(line[len("BENCH_JSON ") :])
    if not payload:
        raise SystemExit("no BENCH_JSON in remote output")
    payload["ssh_wall_ms"] = wall
    (OUT / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    before = {
        "note": "优化前（同场景 S2 / 历史观测）",
        "group_invite": "串行；单家跨云 ReadTimeout 常 10–30s+，整场叠加",
        "group_bid_wait_sec": 45,
        "empty_group_then_rpc": "空等收齐后再串行 RPC",
        "auction_wall_observed": "常 >30–120s（含超时），S2 finish 全链路曾至数分钟",
        "rpc_mode": "for-loop 串行 aip_start_structured",
    }
    after = {
        "note": "优化后（本次实测）",
        "result": payload,
        "changes": [
            "invite asyncio.gather 并行 + ACPS_GROUP_INVITE_TIMEOUT_SEC=5",
            "joined 供应 <2 早停，不再空等 bid wait",
            "ACPS_GROUP_BID_WAIT_SEC 默认 12（原 45）",
            "RPC 回退 asyncio.gather 并行",
            "auction_summary.timings_ms 可观测",
        ],
    }
    md = f"""# 竞价链路时延优化 · 实测

## 优化前（基线）

| 项 | 值 |
|----|----|
| 组群 invite | 串行；跨云单家常超时 10–30s+ |
| 盲拍等待 | 默认 45s |
| 空榜后 | 再串行 RPC |
| 观测墙钟 | 常 >30–120s |

```json
{json.dumps(before, ensure_ascii=False, indent=2)}
```

## 优化后（本次）

| 项 | 值 |
|----|----|
| case | `{payload.get("case_id")}` |
| ok (priced≥2) | `{payload.get("ok")}` |
| transport | `{payload.get("transport")}` |
| early_abort | `{payload.get("early_abort")}` / `{payload.get("abort_reason")}` |
| discover_ms | {payload.get("discover_ms")} |
| rfq_ms | {payload.get("rfq_ms")} |
| **auction_wall_ms** | **{payload.get("auction_wall_ms")}** |
| timings_ms | `{json.dumps(payload.get("auction_timings_ms"), ensure_ascii=False)}` |
| priced | {payload.get("priced")} |
| bids | `{json.dumps(payload.get("bids"), ensure_ascii=False)}` |

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
"""
    (OUT / "REVIEW.md").write_text(md, encoding="utf-8")
    # also refresh rolling summary
    summary_path = OUT.parent / "BEFORE_AFTER.md"
    summary_path.write_text(md, encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    print("WROTE", OUT, flush=True)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main() or 0)
