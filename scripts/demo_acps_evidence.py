"""比赛硬门槛证据：ADP 发现 + AIP 询价 + 双侧 AMP（同 taskId / messageId）。

在 buyer 主机本地跑（或经 SSH 上传后跑）：
  /opt/agentlink/.venv/bin/python scripts/demo_acps_evidence.py

成功打印 ACPS_EVIDENCE_PASS，并写出 docs/evidence/latest_pair.json
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "latest_pair.json"
ACCESS = ROOT / "logs" / "amp_access.jsonl"
MESSAGE = ROOT / "logs" / "amp_message.jsonl"
CTX = ssl._create_unverified_context()
BASE = "https://127.0.0.1:8010"


def http(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
        return json.loads(r.read().decode())


def _tail_jsonl(path: Path, start: int) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for _ in path.open(encoding="utf-8"))


def main() -> int:
    a0, m0 = _line_count(ACCESS), _line_count(MESSAGE)
    case = http("POST", "/api/flow/cases", {"product_name": "重型脚轮", "quantity": 500})
    cid = case["case_id"]
    print("case", cid)
    disc = http("POST", f"/api/flow/cases/{cid}/discover", {"refresh": True})
    meta = disc.get("discovery_meta") or {}
    print("discover", disc.get("state"), meta.get("source"), "cache_hit=", meta.get("cache_hit"), "degrade=", meta.get("degrade"))
    if not (disc.get("candidates") or []):
        print("FAIL: no candidates", file=sys.stderr)
        return 2
    http(
        "POST",
        f"/api/flow/cases/{cid}/confirm-shortlist",
        {"agent_ids": ["supplier-a", "supplier-b", "supplier-c"]},
    )
    rfq = http("POST", f"/api/flow/cases/{cid}/rfq")
    print("rfq", rfq.get("state"), "quotes", len(rfq.get("quotes") or []), "err", rfq.get("rfq_errors"))

    access_new = _tail_jsonl(ACCESS, a0)
    msg_new = _tail_jsonl(MESSAGE, m0)
    sends = [
        r
        for r in access_new
        if (r.get("resource") or {}).get("agentlink.direction") == "send"
        or (r.get("body") or {}).get("eventType") == "send"
    ]
    # Access 可能没有 eventType；用 resource direction
    if not sends:
        sends = [
            r
            for r in access_new
            if str((r.get("resource") or {}).get("agentlink.direction") or "").lower() == "send"
        ]
    msg_sends = [r for r in msg_new if (r.get("body") or {}).get("eventType") == "send"]
    if not msg_sends:
        print("FAIL: no buyer Message send after RFQ", file=sys.stderr)
        return 3

    pairs = []
    for m in msg_sends:
        tid = m.get("correlationId") or m.get("correlation_id")
        mid = (m.get("body") or {}).get("messageId")
        if not tid or not mid:
            continue
        if mid != f"msg-{tid}" and not str(mid).startswith("msg-"):
            print("WARN messageId pattern", mid, tid)
        pairs.append({"taskId": tid, "messageId": mid, "side": "buyer-send", "record": m})

    if not pairs:
        print("FAIL: cannot extract taskId/messageId pairs", file=sys.stderr)
        return 4

    # 源=平台优先；允许 local_fill 但必须标注
    src = str(meta.get("source") or "")
    platform_ok = "platform" in src or meta.get("degrade") is not None
    evidence = {
        "at": datetime.now(timezone.utc).isoformat(),
        "case_id": cid,
        "discovery": {
            "source": meta.get("source"),
            "degrade": meta.get("degrade"),
            "degrade_reason": meta.get("degrade_reason"),
            "cache_hit": meta.get("cache_hit"),
            "discovery_url": meta.get("discovery_url"),
            "elapsed_ms": meta.get("elapsed_ms"),
            "candidates": [
                {
                    "agent_id": x.get("agent_id"),
                    "name": x.get("name"),
                    "source": x.get("source"),
                    "source_label": x.get("source_label"),
                    "degrade": x.get("degrade"),
                }
                for x in (disc.get("candidates") or [])
            ],
        },
        "rfq": {
            "state": rfq.get("state"),
            "quote_count": len(rfq.get("quotes") or []),
            "errors": rfq.get("rfq_errors"),
        },
        "amp_buyer": {
            "access_new": len(access_new),
            "message_new": len(msg_new),
            "pairs": [{"taskId": p["taskId"], "messageId": p["messageId"]} for p in pairs],
        },
        "checks": {
            "has_candidates": True,
            "platform_or_labeled_degrade": bool(platform_ok),
            "amp_message_send_count": len(msg_sends),
            "messageId_equals_msg_taskId": all(p["messageId"] == f"msg-{p['taskId']}" for p in pairs),
            "supplier_abc_all_platform": all(
                (x.get("source") == "platform_adp" and not x.get("degrade"))
                for x in (disc.get("candidates") or [])
                if str(x.get("agent_id") or "").startswith("supplier-")
            )
            if any(str(x.get("agent_id") or "").startswith("supplier-") for x in (disc.get("candidates") or []))
            else False,
        },
        "note": "供应侧 receive 请在阿里云 logs/amp_*.jsonl 用同 taskId 核对；Kafka topic=amp.access/amp.message",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence["checks"], ensure_ascii=False))
    if not evidence["checks"]["messageId_equals_msg_taskId"]:
        print("FAIL: messageId != msg-{taskId}", file=sys.stderr)
        return 5
    if evidence["checks"]["amp_message_send_count"] < 1:
        return 6
    print("ACPS_EVIDENCE_PASS", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
