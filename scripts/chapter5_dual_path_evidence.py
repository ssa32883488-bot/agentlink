# -*- coding: utf-8 -*-
"""第五章取证：普通询价链路 + 组群竞价链路（打远程 buyer-a）。

输出：
  docs/evidence/chapter5_run/
    normal_rfq.json
    group_auction.json
    metrics_snapshot.json
    timeline_*.json
    summary.json
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "chapter5_run"
BASE = "https://ashui.online:8010"
CTX = ssl._create_unverified_context()


def http(method: str, path: str, body: dict | None = None, timeout: int = 300) -> tuple[dict, float]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            raw = r.read().decode()
            ms = (time.perf_counter() - t0) * 1000
            return (json.loads(raw) if raw else {}), ms
    except urllib.error.HTTPError as e:
        ms = (time.perf_counter() - t0) * 1000
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> {e.code}: {detail[:500]}") from e


def step(timeline: list, name: str, fn):
    print(f"==> {name}", flush=True)
    t0 = time.perf_counter()
    try:
        result, http_ms = fn()
        ok = True
        err = None
    except Exception as e:
        result, http_ms, ok, err = {"error": str(e)}, (time.perf_counter() - t0) * 1000, False, str(e)
    wall_ms = (time.perf_counter() - t0) * 1000
    entry = {
        "step": name,
        "ok": ok,
        "http_ms": round(http_ms, 1),
        "wall_ms": round(wall_ms, 1),
        "at": datetime.now(timezone.utc).isoformat(),
        "error": err,
        "result_summary": _summarize(name, result) if ok else None,
        "result": result if ok else {"error": err},
    }
    timeline.append(entry)
    print(f"    ok={ok} http_ms={entry['http_ms']} summary={entry['result_summary']}", flush=True)
    return result if ok else None


def _summarize(name: str, result: dict) -> dict:
    if not isinstance(result, dict):
        return {"type": type(result).__name__}
    out = {"state": result.get("state"), "case_id": result.get("case_id")}
    if name.startswith("discover"):
        meta = result.get("discovery_meta") or {}
        cands = result.get("candidates") or []
        out.update(
            {
                "source": meta.get("source"),
                "degrade": meta.get("degrade"),
                "cache_hit": meta.get("cache_hit"),
                "elapsed_ms_platform": meta.get("elapsed_ms"),
                "candidate_count": len(cands),
                "candidates": [
                    {
                        "agent_id": c.get("agent_id"),
                        "source": c.get("source") or c.get("source_label"),
                        "name": c.get("name"),
                    }
                    for c in cands
                ],
            }
        )
    if name.startswith("rfq"):
        quotes = result.get("quotes") or []
        out.update(
            {
                "quote_count": len(quotes),
                "errors": result.get("rfq_errors") or result.get("errors"),
                "suppliers": [q.get("supplier_agent_id") or q.get("agent_id") for q in quotes],
            }
        )
    if name.startswith("auction"):
        summary = result.get("auction_summary") or {}
        schemes = summary.get("schemes") or []
        bids = result.get("auction_bids") or []
        out.update(
            {
                "transport": summary.get("transport"),
                "bid_count": len(bids),
                "priced": len([b for b in bids if b.get("unit_price") is not None]),
                "scheme_count": len(schemes),
                "best": schemes[0] if schemes else None,
            }
        )
    if name.startswith("decide") or name.startswith("order") or "order" in name:
        draft = (result.get("order_draft") or {}).get("payload") or result.get("order_draft") or {}
        if isinstance(draft, dict):
            out.update(
                {
                    "selected_supplier": result.get("selected_supplier"),
                    "unit_price": draft.get("unit_price"),
                    "shipping_cost": draft.get("shipping_cost"),
                    "goods_total": draft.get("goods_total"),
                    "ticket": result.get("order_ticket_id"),
                }
            )
    if name == "metrics":
        out = {k: result.get(k) for k in list(result)[:20]}
    return out


def run_normal_rfq() -> dict:
    timeline: list = []
    case = step(
        timeline,
        "create_case",
        lambda: http("POST", "/api/flow/cases", {"product_name": "重型脚轮", "quantity": 500, "note": "ch5-normal-rfq"}),
    )
    if not case:
        return {"ok": False, "timeline": timeline}
    cid = case["case_id"]

    disc = step(
        timeline,
        "discover_platform_adp",
        lambda: http("POST", f"/api/flow/cases/{cid}/discover", {"refresh": True}),
    )
    step(
        timeline,
        "confirm_shortlist",
        lambda: http(
            "POST",
            f"/api/flow/cases/{cid}/confirm-shortlist",
            {"agent_ids": ["supplier-a", "supplier-b", "supplier-c"]},
        ),
    )
    rfq = step(timeline, "rfq_parallel_aip", lambda: http("POST", f"/api/flow/cases/{cid}/rfq"))
    # optional shipping / decide order if API allows after compare
    decide = step(
        timeline,
        "decide_order_or_compare",
        lambda: http("POST", f"/api/flow/cases/{cid}/decide", {"action": "order"}),
    )
    metrics, _ = http("GET", "/api/flow/metrics")
    step(timeline, "metrics", lambda: (metrics, 0.0))

    ok = bool(disc and (disc.get("candidates") or [])) and bool(rfq)
    protocol = {
        "wutong_discovery": True,
        "discovery_url": "https://wt.ioa.pub/discovery/acps-adp-v2/discover",
        "aip_rfq": True,
        "amp_expected": "Leader send + Partner receive Access/Message on each RFQ task",
        "agents": ["buyer-a", "supplier-a", "supplier-b", "supplier-c"],
    }
    return {
        "ok": ok,
        "path": "normal_rfq",
        "case_id": cid,
        "timeline": timeline,
        "protocol": protocol,
        "metrics": metrics,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }


def run_group_auction() -> dict:
    timeline: list = []
    case = step(
        timeline,
        "create_case",
        lambda: http(
            "POST",
            "/api/flow/cases",
            {"product_name": "重型脚轮", "quantity": 500, "rated_load_kg_min": 300, "note": "ch5-group-auction"},
        ),
    )
    if not case:
        return {"ok": False, "timeline": timeline}
    cid = case["case_id"]

    step(
        timeline,
        "discover_platform_adp",
        lambda: http("POST", f"/api/flow/cases/{cid}/discover", {"refresh": True}),
    )
    step(
        timeline,
        "confirm_shortlist",
        lambda: http(
            "POST",
            f"/api/flow/cases/{cid}/confirm-shortlist",
            {"agent_ids": ["supplier-a", "supplier-b", "supplier-c"]},
        ),
    )
    step(timeline, "rfq_parallel_aip", lambda: http("POST", f"/api/flow/cases/{cid}/rfq"))
    step(timeline, "decide_auction", lambda: http("POST", f"/api/flow/cases/{cid}/decide", {"action": "auction"}))
    auction = step(timeline, "auction_group_tco", lambda: http("POST", f"/api/flow/cases/{cid}/auction"))
    order = step(timeline, "decide_order_best_tco", lambda: http("POST", f"/api/flow/cases/{cid}/decide", {"action": "order"}))
    metrics, _ = http("GET", "/api/flow/metrics")
    step(timeline, "metrics", lambda: (metrics, 0.0))

    summary = ((auction or {}).get("auction_summary") or {}) if auction else {}
    ok = bool(auction) and summary.get("transport") == "group"
    protocol = {
        "wutong_discovery": True,
        "aip_rfq": True,
        "group_mq": "wt.ioa.pub group plane (auction transport=group)",
        "amp_expected": "RFQ tasks + group auction interactions",
        "agents": ["buyer-a", "supplier-a", "supplier-b", "supplier-c", "logistics(optional)"],
    }
    return {
        "ok": ok,
        "path": "group_auction",
        "case_id": cid,
        "timeline": timeline,
        "protocol": protocol,
        "auction_summary": summary,
        "order_state": (order or {}).get("state") if order else None,
        "metrics": metrics,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "logs").mkdir(exist_ok=True)
    print("BASE", BASE, flush=True)
    health, ms = http("GET", "/health")
    print("health", health, ms, flush=True)

    normal = run_normal_rfq()
    (OUT / "normal_rfq.json").write_text(json.dumps(normal, ensure_ascii=False, indent=2), encoding="utf-8")
    print("NORMAL", normal.get("ok"), normal.get("case_id"), flush=True)

    group = run_group_auction()
    (OUT / "group_auction.json").write_text(json.dumps(group, ensure_ascii=False, indent=2), encoding="utf-8")
    print("GROUP", group.get("ok"), group.get("case_id"), flush=True)

    metrics, _ = http("GET", "/api/flow/metrics")
    (OUT / "metrics_snapshot.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "at": datetime.now(timezone.utc).isoformat(),
        "base": BASE,
        "health": health,
        "normal_ok": normal.get("ok"),
        "group_ok": group.get("ok"),
        "normal_case": normal.get("case_id"),
        "group_case": group.get("case_id"),
        "normal_total_http_ms": sum(s.get("http_ms") or 0 for s in normal.get("timeline") or []),
        "group_total_http_ms": sum(s.get("http_ms") or 0 for s in group.get("timeline") or []),
        "metrics_keys": list(metrics) if isinstance(metrics, dict) else [],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
    print("PASS" if summary["normal_ok"] and summary["group_ok"] else "PARTIAL", flush=True)
    return 0 if summary["normal_ok"] and summary["group_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
