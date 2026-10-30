# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

import paramiko

HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
REMOTE = r"""
python3 - <<'PY'
import json, urllib.request
ok=True
cases=(
 ("supplier-a",18011,"九折"),
 ("supplier-b",18013,"1000"),
 ("supplier-c",18014,"补贴"),
)
for agent,port,needle in cases:
    req=urllib.request.Request(
        "http://127.0.0.1:%d/api/erp/chat"%port,
        data=json.dumps({"text":"你们有什么优惠政策？"}).encode(),
        headers={"content-type":"application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data=json.loads(r.read().decode())
    reply=data.get("reply") or ""
    good = (needle in reply) or ("满" in reply) or ("折" in reply) or ("减" in reply)
    bad_phrases = ("没有优惠字段" in reply) or ("无可报价" in reply) or ("不含任何优惠" in reply)
    print(agent, "OK" if (good and not bad_phrases) else "BAD", data.get("engine"), reply[:160].replace("\n"," | "))
    ok = ok and good and (not bad_phrases) and data.get("engine")=="wit"
print("ALL_PROMO_CHAT_PASS" if ok else "ALL_PROMO_CHAT_FAIL")
PY
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(REMOTE, timeout=400, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    sys.stdout.buffer.write(out.encode("utf-8", errors="replace") + b"\n")
    sys.stdout.buffer.flush()
    c.close()
    return 0 if "ALL_PROMO_CHAT_PASS" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
