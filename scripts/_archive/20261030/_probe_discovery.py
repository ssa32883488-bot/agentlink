"""Probe whether buyer discover hits Wutong ADP or falls back to local ACS."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

REMOTE = r"""
set -e
echo '=== env ==='
grep -E '^ACPS_DISCOVERY_URL=' /opt/agentlink/.env || true

echo '=== latest cases ==='
curl -sk https://127.0.0.1:8010/api/flow/cases -o /tmp/cases.json
python3 -c '
import json
d=json.load(open("/tmp/cases.json"))
items=d.get("items") if isinstance(d,dict) else d
print("n=", len(items or []))
for x in (items or [])[:5]:
  meta=x.get("discovery_meta") or {}
  print("---", x.get("case_id"), x.get("state"))
  print("  source=", meta.get("source"))
  pe=(meta.get("platform_error") or "")
  print("  platform_error=", pe[:200])
  print("  ncand=", len(x.get("candidates") or []))
'

echo '=== ADP probe ==='
python3 -c '
import httpx
base="https://wt.ioa.pub/discovery"
payload={"type":"explicit","query":"工业原料 供应商","limit":3}
for p in ["/discover","/","/v1/discover","/api/discover"]:
  url=base.rstrip("/")+p
  try:
    r=httpx.post(url,json=payload,timeout=12)
    print("POST",p,r.status_code,r.text[:200].replace("\n"," "))
  except Exception as e:
    print("POST",p,type(e).__name__,e)
  try:
    r=httpx.get(url,timeout=12)
    print("GET ",p,r.status_code,r.text[:120].replace("\n"," "))
  except Exception as e:
    print("GET ",p,type(e).__name__,e)
'

echo '=== live discover via buyer ==='
curl -sk -X POST https://127.0.0.1:8010/api/flow/cases -H "Content-Type: application/json" -d "{\"title\":\"probe-discovery\"}" -o /tmp/newcase.json
CID=$(python3 -c 'import json; print(json.load(open("/tmp/newcase.json")).get("case_id",""))')
echo CID=$CID
curl -sk -X POST https://127.0.0.1:8010/api/flow/cases/$CID/discover -H "Content-Type: application/json" -d "{}" -o /tmp/disc.json
python3 -c '
import json
d=json.load(open("/tmp/disc.json"))
meta=d.get("discovery_meta") or {}
print("state", d.get("state"))
print("source", meta.get("source"))
print("platform_error", meta.get("platform_error"))
print("query", meta.get("query"))
print("ncand", len(d.get("candidates") or []))
for c in (d.get("candidates") or [])[:5]:
  print(" -", c.get("agent_id"), c.get("source"), c.get("name"), (c.get("endpoint") or "")[:70])
'
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
    _, stdout, stderr = c.exec_command(REMOTE, timeout=120, get_pty=True)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR:", err[-1000:])
    c.close()


if __name__ == "__main__":
    main()
