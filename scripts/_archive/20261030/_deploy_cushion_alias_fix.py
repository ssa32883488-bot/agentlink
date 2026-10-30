# -*- coding: utf-8 -*-
"""Deploy 坐垫 alias + reject-message extraction; smoke cushion RFQ."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
JARS = {
    "java-suppliers/supplier-a/build/libs/supplier-a-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-a.jar",
    "java-suppliers/supplier-b/build/libs/supplier-b-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-b.jar",
    "java-suppliers/supplier-c/build/libs/supplier-c-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-c.jar",
}


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 300) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def put(c: paramiko.SSHClient, rels: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in rels:
        remote = f"/opt/agentlink/{rel}"
        run(c, f"mkdir -p {'/'.join(remote.split('/')[:-1])}", timeout=20)
        sftp.put(str(ROOT / rel), remote)
        print("put", rel, flush=True)
    sftp.close()


def main() -> None:
    print("==== ALIYUN ====", flush=True)
    a = paramiko.SSHClient()
    a.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    a.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(a, ["agents/supplier_common/catalog_price.py"])
    with SCPClient(a.get_transport()) as scp:
        for local, remote in JARS.items():
            scp.put(str(ROOT / local), remote)
            print("jar", remote, flush=True)
    print(
        run(
            a,
            "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
            "for i in $(seq 1 24); do "
            "x=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8011/health||true); "
            "y=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8013/health||true); "
            "z=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8014/health||true); "
            "echo try$i $x$y$z; [ \"$x$y$z\" = 200200200 ] && break; sleep 5; done",
            timeout=200,
        ),
        flush=True,
    )
    a.close()

    print("==== TENCENT ====", flush=True)
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
    put(
        b,
        [
            "agents/supplier_common/catalog_price.py",
            "agentlink_runtime/aip_client_util.py",
            "commerce/chat_buyer_wit.py",
            "commerce/buyer_tools/service.py",
        ],
    )
    print(
        run(
            b,
            r"""
systemctl restart agentlink-buyer-a agentlink-buyer-b
sleep 6
cd /opt/agentlink && .venv/bin/python - <<'PY'
import asyncio, json, os
from pathlib import Path
for f in ('/opt/agentlink/.env','/etc/agentlink/buyer-b.env','/etc/agentlink/buyer-a.env'):
    p=Path(f)
    if not p.is_file():
        continue
    for raw in p.read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1)
        os.environ[k.strip()]=v.strip().strip('"').strip("'")
os.environ['BUYER_AGENT_ID']='buyer-b'
from commerce.buyer_tools.service import get_buyer_tools
from agents.supplier_common.catalog_price import requested_sku
print('alias_cushion', requested_sku(product_name='坐垫'))
async def main():
    tools=get_buyer_tools()
    disc=await tools.discover_suppliers_tool({'product_name':'坐垫','quantity':300,'query':'坐垫 海绵','limit':5,'refresh':True})
    selected=[c.get('candidate_id') for c in (disc.get('candidates') or [])[:3] if c.get('candidate_id')] or ['supplier-a','supplier-b','supplier-c']
    out=await tools.rfq_send_batch({'case_id': disc.get('case_id'), 'selected': selected})
    rows=[]
    for q in out.get('quotes') or []:
        p=q.get('partner') or {}
        rows.append({'id':p.get('agent_id'),'status':q.get('status'),'unit':(q.get('line_prices') or [{}])[0].get('unit_price') if q.get('line_prices') else None,'goods':q.get('goods_total'),'err':(q.get('error') or '')[:160]})
    print(json.dumps({'case':disc.get('case_id'),'summary':out.get('summary'),'rows':rows}, ensure_ascii=False, indent=2))
    a=next((r for r in rows if r['id']=='supplier-a'), None)
    b=next((r for r in rows if r['id']=='supplier-b'), None)
    c=next((r for r in rows if r['id']=='supplier-c'), None)
    ok = (a and a['status']=='error' and b and b['status']=='ok' and c and c['status']=='ok')
    print('CUSHION_RFQ_PASS' if ok else 'CUSHION_RFQ_FAIL')
asyncio.run(main())
PY
""",
            timeout=300,
        ),
        flush=True,
    )
    b.close()


if __name__ == "__main__":
    main()
