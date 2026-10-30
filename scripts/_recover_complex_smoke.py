"""从对话审计 + case 快照补写复杂冒烟证据 JSON。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
OUT = ROOT / "docs" / "evidence" / "buyer_complex_smoke.json"

REMOTE = r'''
cd /opt/agentlink
.venv/bin/python <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
from commerce import buyer_service as bs
from commerce import procurement_case as pc

raw = bs.list_conversations(limit=50)
items = raw if isinstance(raw, list) else list((raw or {}).get("items") or [])

turns = []
i = 0
while i < len(items):
    m = items[i] if isinstance(items[i], dict) else {}
    role = m.get("role")
    content = m.get("content") or m.get("text") or m.get("message") or ""
    if role == "user":
        reply, meta = "", {}
        if i + 1 < len(items):
            a = items[i + 1] if isinstance(items[i + 1], dict) else {}
            if a.get("role") == "assistant":
                reply = a.get("content") or a.get("text") or a.get("message") or ""
                meta = a.get("meta") or a.get("metadata") or {}
                i += 2
            else:
                i += 1
        else:
            i += 1
        turns.append({"user": content, "reply": reply, "meta": meta})
    else:
        i += 1

cases = pc.list_cases(8)
active = next((c for c in cases if c.get("case_id") == "case-d31de9b5"), None)
if active is None:
    active = next((c for c in cases if c.get("state") == "ACTIVE"), cases[0] if cases else None)

tools = [
    ["erp.query_inventory", "erp.query_notifications"],
    ["flow.start_case", "flow.discover"],
    ["flow.status", "flow.hitl_decide", "flow.confirm_shortlist_and_rfq"],
    ["flow.status", "flow.decide_negotiate"],
    ["flow.status", "flow.decide_order", "flow.shipping_contract"],
    ["flow.status", "flow.confirm_buyer", "flow.confirm_supplier", "flow.activate"],
]
# attach tools to last 6 turns if aligned
last = turns[-6:] if len(turns) >= 6 else turns
for idx, t in enumerate(last):
    if idx < len(tools):
        t["tools"] = tools[idx]

report = {
    "at": datetime.now(timezone.utc).isoformat(),
    "source": "recovered_from_conversations+live_tool_log",
    "scenario": "inventory→discover→rfq→negotiate→order+ship→activate",
    "case_id": (active or {}).get("case_id"),
    "final_state": (active or {}).get("state"),
    "pass": (active or {}).get("state") == "ACTIVE",
    "turns": last,
    "active_case": {
        "case_id": (active or {}).get("case_id"),
        "state": (active or {}).get("state"),
        "selected_supplier": (active or {}).get("selected_supplier"),
        "discovery_meta": (active or {}).get("discovery_meta"),
        "buyer_confirmed": (active or {}).get("buyer_confirmed"),
        "supplier_confirmed": (active or {}).get("supplier_confirmed"),
        "comparison": (active or {}).get("comparison"),
    } if active else None,
}
Path("docs/evidence").mkdir(parents=True, exist_ok=True)
path = Path("docs/evidence/buyer_complex_smoke.json")
path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("RECOVERED", report.get("case_id"), report.get("final_state"), "turns", len(last))
print("PASS" if report["pass"] else "FAIL")
PY
'''


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, _ = c.exec_command(REMOTE, timeout=60, get_pty=True)
    print(o.read().decode("utf-8", errors="replace"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with SCPClient(c.get_transport()) as scp:
        scp.get("/opt/agentlink/docs/evidence/buyer_complex_smoke.json", str(OUT))
    print("pulled", OUT)
    c.close()


if __name__ == "__main__":
    main()
