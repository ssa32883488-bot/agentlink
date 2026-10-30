"""Remote smoke: HITL reject + metrics after deploy."""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE_SH = r"""
set -e
cd /opt/agentlink
systemctl restart agentlink-buyer-a
sleep 6
/opt/agentlink/.venv/bin/python <<'PY'
import json, ssl, urllib.error, urllib.request
from commerce import procurement_case as pc
from commerce.hitl_gate import make_hitl

CTX = ssl._create_unverified_context()
BASE = "https://127.0.0.1:8010"

def http(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.loads(r.read().decode())

case = http("POST", "/api/flow/cases", {"product_name": "脚轮", "quantity": 10})
cid = case["case_id"]
pc.transition(cid, "DISCOVERING", event="t")
pc.transition(
    cid,
    "SHORTLIST_PENDING",
    event="t2",
    patch={
        "candidates": [
            {
                "agent_id": "supplier-a",
                "name": "A",
                "aic": "x",
                "endpoint": "http://x",
                "source": "platform_adp",
                "source_label": "平台发现",
            }
        ],
        "hitl_pending": make_hitl("confirm_shortlist", "请确认"),
    },
)
rej = http("POST", f"/api/flow/cases/{cid}/hitl", {"decision": "reject", "note": "验收拒绝"})
assert rej.get("voided") and rej.get("state") == "EXCEPTION", rej
try:
    http("POST", f"/api/flow/cases/{cid}/confirm-shortlist", {"agent_ids": ["supplier-a"]})
    raise SystemExit("reject should block shortlist")
except urllib.error.HTTPError as e:
    print("reject_blocks_ok", e.code)
except Exception as e:
    print("reject_blocks_ok", type(e).__name__, e)

# idempotent shortlist
case2 = http("POST", "/api/flow/cases", {"product_name": "脚轮", "quantity": 20})
cid2 = case2["case_id"]
pc.transition(cid2, "DISCOVERING", event="a")
pc.transition(
    cid2,
    "SHORTLIST_PENDING",
    event="b",
    patch={
        "candidates": [
            {"agent_id": "supplier-a", "name": "A", "aic": "a", "endpoint": "http://a"}
        ],
        "hitl_pending": make_hitl("confirm_shortlist", "请确认"),
    },
)
s1 = http("POST", f"/api/flow/cases/{cid2}/confirm-shortlist", {"agent_ids": ["supplier-a"]})
s2 = http("POST", f"/api/flow/cases/{cid2}/confirm-shortlist", {"agent_ids": ["supplier-a"]})
assert s1["state"] == s2["state"] == "SOURCING", (s1["state"], s2["state"])
print("idempotent_shortlist_ok", cid2)

m = http("GET", "/api/flow/metrics")
print("kpi", json.dumps(m.get("kpi"), ensure_ascii=False))
print("HITL_SMOKE_PASS")
PY
"""


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
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(ROOT / "commerce/amp_metrics.py"), "/opt/agentlink/commerce/amp_metrics.py")
    _, stdout, _ = c.exec_command(REMOTE_SH, timeout=90, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
