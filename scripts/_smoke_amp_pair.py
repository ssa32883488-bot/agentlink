"""Restart services and smoke bilateral AMP via real AIP RFQ hop."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def connect(host: str, *, password: str | None = None) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        c.connect(host, username="root", password=password, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            host,
            username="root",
            pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    print(out[-4000:])
    return out


def main() -> None:
    buyer = connect("81.70.46.119")
    supplier = connect("39.105.20.113", password=os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"))

    print("==== restart ====")
    run(buyer, "systemctl restart agentlink-buyer-a agentlink-logistics; sleep 3; systemctl is-active agentlink-buyer-a")
    run(supplier, "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 3; systemctl is-active agentlink-supplier-a")

    print("==== real RFQ via flow (creates AIP + AMP) ====")
    run(
        buyer,
        r"""
cd /opt/agentlink
# mark log offsets
A0=$(wc -l < logs/amp_access.jsonl 2>/dev/null || echo 0)
M0=$(wc -l < logs/amp_message.jsonl 2>/dev/null || echo 0)
curl -sk -X POST https://127.0.0.1:8010/api/flow/cases -H 'Content-Type: application/json' \
  -d '{"title":"amp-pair","brief":{"product_name":"重型脚轮","quantity":500}}' -o /tmp/nc.json
CID=$(python3 -c 'import json;print(json.load(open("/tmp/nc.json")).get("case_id",""))')
echo CID=$CID
curl -sk -X POST https://127.0.0.1:8010/api/flow/cases/$CID/discover -H 'Content-Type: application/json' -d '{}' -o /tmp/d.json
python3 -c 'import json;d=json.load(open("/tmp/d.json"));print(d.get("state"), (d.get("discovery_meta") or {}).get("source"), len(d.get("candidates") or []))'
# confirm shortlist + rfq
curl -sk -X POST https://127.0.0.1:8010/api/flow/cases/$CID/confirm-shortlist \
  -H 'Content-Type: application/json' \
  -d '{"agent_ids":["supplier-a","supplier-b","supplier-c"]}' -o /tmp/sl.json
curl -sk -X POST https://127.0.0.1:8010/api/flow/cases/$CID/rfq -o /tmp/rfq.json
python3 -c 'import json;d=json.load(open("/tmp/rfq.json"));print("rfq", d.get("state"), "quotes", len(d.get("quotes") or []), "err", d.get("rfq_errors"))'
sleep 1
echo "--- buyer new amp lines ---"
python3 - <<PY
from pathlib import Path
import json
A0=int("$A0"); M0=int("$M0")
for name,start in [("amp_access.jsonl",A0),("amp_message.jsonl",M0)]:
  p=Path("logs")/name
  lines=p.read_text(encoding="utf-8").splitlines() if p.exists() else []
  new=lines[start:]
  print(name, "new", len(new))
  for line in new[-6:]:
    r=json.loads(line)
    body=r.get("body") or {}
    print(" ", r.get("log_type"), "corr=", r.get("correlationId") or r.get("correlation_id"),
          "dir=", (r.get("resource") or {}).get("agentlink.direction"),
          "evt=", body.get("eventType"), "mid=", body.get("messageId"))
PY
""",
        timeout=180,
    )

    print("==== supplier amp tail ====")
    run(
        supplier,
        r"""
cd /opt/agentlink
python3 - <<'PY'
from pathlib import Path
import json
for name in ("amp_access.jsonl","amp_message.jsonl"):
  p=Path("logs")/name
  lines=p.read_text(encoding="utf-8").splitlines() if p.exists() else []
  print(name, "total", len(lines))
  for line in lines[-4:]:
    r=json.loads(line)
    body=r.get("body") or {}
    print(" ", r.get("log_type"), "corr=", r.get("correlationId") or r.get("correlation_id"),
          "dir=", (r.get("resource") or {}).get("agentlink.direction"),
          "evt=", body.get("eventType"), "mid=", body.get("messageId"),
          "aic=", (r.get("aic") or "")[-18:])
PY
""",
    )
    buyer.close()
    supplier.close()


if __name__ == "__main__":
    main()
