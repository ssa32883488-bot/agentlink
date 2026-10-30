# -*- coding: utf-8 -*-
"""Aggregate AMP access/message logs + evidence metrics for Chapter 5."""
from __future__ import annotations

import json
import ssl
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "chapter5_run" / "interaction_aggregate.json"
ACCESS = ROOT / "logs" / "amp_access.jsonl"
MESSAGE = ROOT / "logs" / "amp_message.jsonl"
CTX = ssl._create_unverified_context()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarize(rows: list[dict], kind: str) -> dict:
    by_day = Counter()
    by_status = Counter()
    by_dir = Counter()
    tasks = set()
    msgs = set()
    peers = Counter()
    for r in rows:
        ts = str(r.get("at") or r.get("timestamp") or r.get("time") or "")
        day = ts[:10] if len(ts) >= 10 else "unknown"
        by_day[day] += 1
        st = str(r.get("status") or r.get("http_status") or r.get("state") or "unknown")
        by_status[st] += 1
        by_dir[str(r.get("direction") or "unknown")] += 1
        tid = str(r.get("taskId") or r.get("task_id") or "")
        mid = str(r.get("messageId") or r.get("message_id") or "")
        if tid:
            tasks.add(tid)
        if mid:
            msgs.add(mid)
        peer = str(r.get("peerAic") or r.get("peer_aic") or r.get("to_aic") or "")[:24]
        if peer:
            peers[peer] += 1
    # success heuristic
    ok_keys = {"ok", "200", "completed", "success", "awaiting-completion", "awaiting-input"}
    ok_n = sum(n for k, n in by_status.items() if any(x in k.lower() for x in ("ok", "200", "complet", "await", "success")))
    total = len(rows) or 1
    return {
        "kind": kind,
        "total": len(rows),
        "unique_tasks": len(tasks),
        "unique_messages": len(msgs),
        "by_day": dict(sorted(by_day.items())),
        "by_status": dict(by_status.most_common()),
        "by_direction": dict(by_dir),
        "top_peers": peers.most_common(8),
        "success_like_rate": round(ok_n / total, 4),
    }


def fetch_live_metrics() -> dict | None:
    for url in (
        "https://ashui.online:8010/api/flow/metrics",
        "https://81.70.46.119:8010/api/flow/metrics",
    ):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25, context=CTX) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:  # noqa: BLE001
            last = str(e)
    return {"error": last}


def main() -> None:
    access = load_jsonl(ACCESS)
    message = load_jsonl(MESSAGE)
    live = fetch_live_metrics()
    snap = {}
    snap_path = ROOT / "docs/evidence/chapter5_run/metrics_snapshot.json"
    if snap_path.exists():
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    latency = {}
    lat_path = ROOT / "docs/evidence/latency_opt/bench_20261030_043713/result.json"
    if lat_path.exists():
        latency = json.loads(lat_path.read_text(encoding="utf-8"))

    # evidence case counts from verify_ui_shots reports
    cases = []
    for p in (ROOT / "docs/evidence").rglob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and ("case_id" in d or "timeline" in d or "kpi" in d):
            cases.append({"path": str(p.relative_to(ROOT)), "keys": list(d.keys())[:8]})

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "local_amp_access": summarize(access, "access"),
        "local_amp_message": summarize(message, "message"),
        "live_metrics": live,
        "snapshot_20261029": snap,
        "latency_opt_bench": latency,
        "evidence_json_files_sampled": len(cases),
        "notes": [
            "local jsonl may be partial vs cloud; prefer live_metrics when available",
            "success_like_rate treats awaiting/200/ok as successful interaction states",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:4000])
    print("saved", OUT)


if __name__ == "__main__":
    main()
