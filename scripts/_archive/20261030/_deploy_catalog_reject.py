# -*- coding: utf-8 -*-
"""Deploy no-wrong-SKU quote fix; smoke chair-frame RFQ (B must reject)."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

PY = [
    "agents/supplier_common/catalog_price.py",
    "agents/supplier_a/pricing.py",
    "agents/supplier_a/graph.py",
    "agents/supplier_b/graph.py",
    "agents/supplier_c/graph.py",
    "commerce/buyer_tools/service.py",
    "commerce/chat_buyer_wit.py",
]
JARS = {
    "java-suppliers/supplier-a/build/libs/supplier-a-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-a.jar",
    "java-suppliers/supplier-b/build/libs/supplier-b-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-b.jar",
    "java-suppliers/supplier-c/build/libs/supplier-c-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-c.jar",
}


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 300) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def main() -> int:
    for rel in JARS:
        if not (ROOT / rel).is_file():
            print("MISSING", rel)
            return 2

    print("==== ALIYUN jars+py ====", flush=True)
    a = paramiko.SSHClient()
    a.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    a.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    sftp = a.open_sftp()
    for rel in PY:
        remote = f"/opt/agentlink/{rel}"
        parent = "/".join(remote.split("/")[:-1])
        run(a, f"mkdir -p {parent}", timeout=30)
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()
    with SCPClient(a.get_transport()) as scp:
        for local, remote in JARS.items():
            scp.put(str(ROOT / local), remote)
            print("put", local, "->", remote, flush=True)
    print(
        run(
            a,
            r"""
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp 2>/dev/null || true
for i in $(seq 1 24); do
  x=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8011/health || true)
  y=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8013/health || true)
  z=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8014/health || true)
  echo try$i $x$y$z
  [ "$x$y$z" = 200200200 ] && break
  sleep 5
done
for p in 8011 8013 8014; do echo -n H:$p; curl -sk https://127.0.0.1:$p/health; echo; done
""",
            timeout=200,
        ),
        flush=True,
    )
    a.close()

    print("==== TENCENT buyer ====", flush=True)
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = b.open_sftp()
    for rel in ("commerce/buyer_tools/service.py", "commerce/chat_buyer_wit.py", "agents/supplier_common/catalog_price.py"):
        remote = f"/opt/agentlink/{rel}"
        parent = "/".join(remote.split("/")[:-1])
        run(b, f"mkdir -p {parent}", timeout=30)
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()
    print(
        run(
            b,
            r"""
systemctl restart agentlink-buyer-a agentlink-buyer-b
sleep 6
systemctl is-active agentlink-buyer-a
cd /opt/agentlink && .venv/bin/python - <<'PY'
import asyncio, json, os
from pathlib import Path
for f in ('/opt/agentlink/.env','/etc/agentlink/buyer-a.env'):
    p=Path(f)
    if not p.is_file(): continue
    for raw in p.read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1)
        os.environ[k.strip()]=v.strip().strip('"').strip("'")
os.environ['BUYER_AGENT_ID']='buyer-a'
from commerce.buyer_tools.service import get_buyer_tools
async def main():
    tools=get_buyer_tools()
    disc=await tools.discover_suppliers_tool({
        'product_name':'钢管制件椅架','quantity':300,'query':'椅架 钢管','limit':5,'refresh':True
    })
    print('case', disc.get('case_id'), 'n', len(disc.get('candidates') or []))
    selected=[c.get('candidate_id') for c in (disc.get('candidates') or [])[:3] if c.get('candidate_id')]
    if len(selected)<3:
        selected=['supplier-a','supplier-b','supplier-c']
    out=await tools.rfq_send_batch({'case_id': disc.get('case_id'), 'selected': selected})
    rows=[]
    for q in out.get('quotes') or []:
        p=q.get('partner') or {}
        rows.append({
            'id': p.get('agent_id'),
            'status': q.get('status'),
            'goods': q.get('goods_total'),
            'unit': (q.get('line_prices') or [{}])[0].get('unit_price') if q.get('line_prices') else None,
            'err': (q.get('error') or '')[:180],
        })
    print(json.dumps({'summary': out.get('summary'), 'rows': rows}, ensure_ascii=False, indent=2))
    b=next((r for r in rows if r['id']=='supplier-b'), None)
    a=next((r for r in rows if r['id']=='supplier-a'), None)
    c=next((r for r in rows if r['id']=='supplier-c'), None)
    ok = (b and b['status']=='error' and a and a['status']=='ok' and c and c['status']=='ok'
          and a.get('unit')==85 and c.get('unit')==100)
    print('CATALOG_REJECT_PASS' if ok else 'CATALOG_REJECT_FAIL')
asyncio.run(main())
PY
""",
            timeout=300,
        ),
        flush=True,
    )
    b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
