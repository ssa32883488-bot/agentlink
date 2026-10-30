"""复杂任务冒烟：多轮对话驱动采购商A，记录 SSE 全程到 docs/evidence/buyer_complex_smoke.json."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
OUT = ROOT / "docs" / "evidence" / "buyer_complex_smoke.json"

# 多轮：先查再规划，再发现/询价/议价旁路到下单/物流/确认/激活
TURNS = [
    "先看看现在原料库存有没有低于安全线，以及最近有没有未读通知。根据情况告诉我要不要启动正式采购。",
    "启动正式采购：产品「重型脚轮」，数量 500，额定载荷至少 300kg。先去梧桐平台发现供应商，不要直接询价。",
    "确认三家供应商A/B/C，发起 AIP 询价，把报价对比结果告诉我。",
    "先不要直接下单。发起一轮议价，目标是保质保交期前提下优化总价，议完再告诉我对比结果。",
    "选当前对比里最优的供应商生成订单草案，然后合入物流运费生成合同。",
    "采购方确认合同，再请求供应商确认，最后激活订单。",
]

REMOTE = r'''
cd /opt/agentlink
.venv/bin/python <<'PY'
import json, ssl, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

CTX = ssl._create_unverified_context()
BASE = "https://127.0.0.1:8010"
TURNS = ''' + json.dumps(TURNS, ensure_ascii=False) + r'''

def post_stream(text: str) -> dict:
    req = urllib.request.Request(
        BASE + "/api/erp/chat/stream",
        data=json.dumps({"text": text}, ensure_ascii=False).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    events = []
    tokens = []
    tools = []
    statuses = []
    done = None
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600, context=CTX) as resp:
        buf = b""
        while True:
            chunk = resp.read(256)
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf:
                block, buf = buf.split(b"\n\n", 1)
                for line in block.split(b"\n"):
                    if not line.startswith(b"data:"):
                        continue
                    raw = line[5:].strip().decode("utf-8", errors="replace")
                    if not raw:
                        continue
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    typ = ev.get("type")
                    events.append({"t": round(time.time()-t0, 2), **{k: ev[k] for k in ev if k != "text" or typ != "token"}})
                    if typ == "token":
                        tokens.append(ev.get("text") or "")
                        # keep compact event without full token flood
                        events[-1] = {"t": events[-1]["t"], "type": "token", "len": len(ev.get("text") or "")}
                    elif typ == "status":
                        statuses.append({"t": events[-1]["t"], "phase": ev.get("phase"), "text": ev.get("text"), "tool": ev.get("tool")})
                    elif typ in ("tool",) or ev.get("tool"):
                        if typ in ("status",) and ev.get("phase") in ("tool", "tool_done"):
                            tools.append({"t": events[-1]["t"], "phase": ev.get("phase"), "tool": ev.get("tool"), "text": ev.get("text")})
                    elif typ == "done":
                        done = {k: v for k, v in ev.items() if k != "type"}
                    elif typ == "error":
                        done = {"error": ev.get("message"), "intent": ev.get("intent")}
                    elif typ == "close":
                        pass
    # rebuild tools from statuses
    tools = [s for s in statuses if s.get("phase") in ("tool", "tool_done")]
    return {
        "elapsed_sec": round(time.time() - t0, 2),
        "user": text,
        "reply": (done or {}).get("reply") or "".join(tokens),
        "done": done,
        "statuses": statuses,
        "tools_timeline": tools,
        "token_chars": sum(len(x) for x in tokens),
        "event_count": len(events),
    }

report = {
    "at": datetime.now(timezone.utc).isoformat(),
    "scenario": "complex multi-turn buyer agent: inventory → discover → rfq → negotiate → order+ship → confirm → activate",
    "turns": [],
}
for i, text in enumerate(TURNS, 1):
    print(f"=== TURN {i}/{len(TURNS)} ===", flush=True)
    print(text[:80], flush=True)
    try:
        turn = post_stream(text)
    except Exception as e:
        turn = {"user": text, "error": str(e)}
    report["turns"].append({"index": i, **turn})
    print("reply_preview:", (turn.get("reply") or turn.get("error") or "")[:200], flush=True)
    tls = turn.get("tools_timeline") or []
    print("tools:", [(t.get("phase"), t.get("tool")) for t in tls], flush=True)
    time.sleep(1)

# case snapshot
try:
    req = urllib.request.Request(BASE + "/api/flow/cases", method="GET")
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        cases = json.loads(r.read().decode())
    report["latest_cases"] = (cases.get("items") or [])[:3]
except Exception as e:
    report["latest_cases_error"] = str(e)

Path("docs/evidence").mkdir(parents=True, exist_ok=True)
Path("docs/evidence/buyer_complex_smoke.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("SMOKE_COMPLEX_WRITTEN")
# summary line
ok = all("error" not in t for t in report["turns"])
print("SMOKE_COMPLEX_PASS" if ok else "SMOKE_COMPLEX_PARTIAL")
PY
'''


def main() -> None:
    # also deploy hitl_decide fix
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
        scp.put(str(ROOT / "commerce/chat_buyer_wit.py"), "/opt/agentlink/commerce/chat_buyer_wit.py")
    _, o, _ = c.exec_command(
        "systemctl restart agentlink-buyer-a; sleep 5; systemctl is-active agentlink-buyer-a",
        timeout=60,
        get_pty=True,
    )
    print(o.read().decode("utf-8", errors="replace"))
    print("==== complex chat smoke (may take several minutes) ====")
    _, o2, _ = c.exec_command(REMOTE, timeout=900, get_pty=True)
    print(o2.read().decode("utf-8", errors="replace")[-12000:])
    with SCPClient(c.get_transport()) as scp:
        (ROOT / "docs" / "evidence").mkdir(parents=True, exist_ok=True)
        scp.get(
            "/opt/agentlink/docs/evidence/buyer_complex_smoke.json",
            str(OUT),
        )
    print("pulled", OUT)
    c.close()


if __name__ == "__main__":
    main()
