# -*- coding: utf-8 -*-
"""诊断：线上 thread 消息是否落库；conversations API 是否返回。"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _i, o, e = c.exec_command(cmd, timeout=60)
    out = o.read().decode("utf-8", errors="replace")
    err = e.read().decode("utf-8", errors="replace")
    return (out + err).strip()


def main() -> None:
    c = connect()
    print("=== files ===")
    print(run(c, "ls -la /opt/agentlink/data/v2_threads/ 2>/dev/null; ls -la /opt/agentlink/data/v2_cases/ 2>/dev/null | head"))
    print("=== thread dump ===")
    print(
        run(
            c,
            r"""python3 -c '
import json, pathlib
p=pathlib.Path("/opt/agentlink/data/v2_threads")
for f in sorted(p.glob("*.json")):
  d=json.loads(f.read_text())
  ths=d.get("threads") or {}
  print("===", f.name, "active=", d.get("active"), "n=", len(ths))
  for tid,t in list(ths.items())[:10]:
    msgs=t.get("messages") or []
    print(" ", tid, "status=", t.get("status"), "title=", (t.get("title") or "")[:40], "msgs=", len(msgs), "case=", t.get("case_id"))
    if msgs:
      print("   first:", msgs[0].get("role"), str(msgs[0].get("content") or "")[:80])
      print("   last:", msgs[-1].get("role"), str(msgs[-1].get("content") or "")[:80])
'
""",
        )
    )
    print("=== case history lens ===")
    print(
        run(
            c,
            r"""python3 -c '
import json, pathlib
p=pathlib.Path("/opt/agentlink/data/v2_cases")
for f in sorted(p.glob("buyer*.json"))[:6]:
  d=json.loads(f.read_text())
  cases=d.get("cases") or d
  if isinstance(cases, dict) and "cases" not in d:
    items=list(cases.values()) if all(isinstance(v, dict) for v in cases.values()) else []
  else:
    items=list((d.get("cases") or {}).values())
  print("===", f.name)
  for c in items[:5]:
    if not isinstance(c, dict):
      continue
    h=c.get("history") or []
    print(" ", c.get("case_id"), "state=", c.get("state"), "hist=", len(h), "order=", c.get("order_id"), "logistics=", c.get("logistics_id"))
'
""",
        )
    )
    print("=== local curl conversations ===")
    print(
        run(
            c,
            "curl -sk http://127.0.0.1:8010/api/erp/conversations?limit=5 | python3 -m json.tool 2>/dev/null | head -80; "
            "curl -sk http://127.0.0.1:8010/api/erp/chat/threads | python3 -m json.tool 2>/dev/null | head -60",
        )
    )
    print("=== app.js mtime / loadChatHistory present ===")
    print(
        run(
            c,
            "ls -la /opt/agentlink/ui/static/app.js /opt/agentlink_bundle/agentlink/ui/static/app.js 2>/dev/null; "
            "grep -n 'loadChatHistory\\|conversations' /opt/agentlink/ui/static/app.js | head -20; "
            "systemctl show agentlink-ui-buyer-a -p FragmentPath -p WorkingDirectory --no-pager; "
            "grep -n 'static\|StaticFiles\|/opt/agentlink' /opt/agentlink/ui/app.py 2>/dev/null | head -20",
        )
    )
    c.close()


if __name__ == "__main__":
    main()
