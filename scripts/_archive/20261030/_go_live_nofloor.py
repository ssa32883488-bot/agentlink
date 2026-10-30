# -*- coding: utf-8 -*-
"""全量上线：腾讯采购/物流 + 阿里云 Java 供应（无底价 / 仅优惠政策）。"""
from __future__ import annotations

import os
import sys
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
BUYER_HOST = "81.70.46.119"
SUPPLIER_HOST = "39.105.20.113"

SHARED_FILES = [
    "agents/supplier_a/policy.yaml",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_c/policy.yaml",
    "agents/supplier_common/promo.py",
    "agents/supplier_common/negotiate.py",
    "agents/supplier_common/catalog_price.py",
    "commerce/seat_catalog.py",
    "commerce/seed.py",
    "commerce/scheme_planner.py",
    "commerce/merchant_profiles.yaml",
    "docs/six_agents_tech_stack_and_params.md",
]

BUYER_EXTRA = [
    "agents/buyer_a/policy.yaml",
    "agents/buyer_b/policy.yaml",
    "agents/logistics/policy.yaml",
    "agents/logistics/graph.py",
]

ALIYUN_EXTRA = [
    "ui/app.py",
    "ui/static/app.js",
]

JARS = [
    ("supplier-a", ROOT / "java-suppliers/supplier-a/build/libs/supplier-a-0.1.0.jar"),
    ("supplier-b", ROOT / "java-suppliers/supplier-b/build/libs/supplier-b-0.1.0.jar"),
    ("supplier-c", ROOT / "java-suppliers/supplier-c/build/libs/supplier-c-0.1.0.jar"),
]


def connect(host: str, *, password: str | None = None) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        c.connect(host, username="root", password=password, timeout=45, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            host,
            username="root",
            pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
            timeout=45,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 300) -> str:
    print(f"$ {cmd[:160]}{'...' if len(cmd) > 160 else ''}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    if out.strip():
        print(out[-8000:], flush=True)
    return out


def put_files(c: paramiko.SSHClient, rels: list[str]) -> None:
    with SCPClient(c.get_transport()) as scp:
        for rel in rels:
            local = ROOT / rel
            if not local.is_file():
                print("skip missing", rel, flush=True)
                continue
            remote = f"/opt/agentlink/{rel.replace(chr(92), '/')}"
            parent = remote.rsplit("/", 1)[0]
            run(c, f"mkdir -p {parent}", timeout=20)
            scp.put(str(local), remote)
            print("put", rel, flush=True)


def put_jars(c: paramiko.SSHClient) -> None:
    run(c, "mkdir -p /opt/agentlink/java-suppliers /var/log/agentlink", timeout=20)
    with SCPClient(c.get_transport()) as scp:
        for name, path in JARS:
            if not path.is_file():
                raise SystemExit(f"missing jar {path}")
            remote = f"/opt/agentlink/java-suppliers/{name}.jar"
            scp.put(str(path), remote)
            print("put jar", name, path.stat().st_size, flush=True)


def deploy_tencent() -> None:
    print("==== Tencent buyer/logistics ====", flush=True)
    c = connect(BUYER_HOST)
    put_files(c, SHARED_FILES + BUYER_EXTRA)
    run(
        c,
        """
set -e
cd /opt/agentlink
.venv/bin/python -m commerce.seed || true
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics || true
sleep 4
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics || true
curl -sk -m 8 https://127.0.0.1:8010/health || true; echo
curl -sk -m 8 https://127.0.0.1:8012/health || true; echo
curl -sk -m 8 https://127.0.0.1:8015/health || true; echo
""",
        timeout=120,
    )
    c.close()


def deploy_aliyun() -> None:
    print("==== Aliyun Java suppliers + ERP + UI ====", flush=True)
    c = connect(SUPPLIER_HOST, password=PW)
    put_files(c, SHARED_FILES + ALIYUN_EXTRA)
    put_jars(c)
    # keep ERP_UPSTREAM in units if already present
    run(
        c,
        r"""
set -e
cd /opt/agentlink
.venv/bin/python -m commerce.seed

# ensure ERP_UPSTREAM on java units without wiping TLS/other env
for name in supplier-a supplier-b supplier-c; do
  f=/etc/systemd/system/agentlink-${name}.service
  case $name in
    supplier-a) port=18011;;
    supplier-b) port=18013;;
    supplier-c) port=18014;;
  esac
  if [ -f "$f" ] && ! grep -q ERP_UPSTREAM "$f"; then
    sed -i "/EnvironmentFile=-\\/etc\\/agentlink\\/${name}.env/a Environment=ERP_UPSTREAM=http://127.0.0.1:${port}" "$f"
  fi
done
systemctl daemon-reload

systemctl restart \
  agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c \
  agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp \
  agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c || true

# wait java health
ok=0
for i in $(seq 1 16); do
  if curl -sk -m 4 https://127.0.0.1:8011/health | grep -q '"runtime":"java"'; then
    echo java_ready_$i
    ok=1
    break
  fi
  echo wait_java_$i
  sleep 5
done
[ "$ok" = 1 ] || { echo 'java health timeout'; tail -n 40 /var/log/agentlink/supplier-a.log; exit 1; }

systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c \
  agentlink-supplier-a-erp agentlink-ui-supplier-a || true
echo '--- health ---'
curl -sk -m 8 https://127.0.0.1:8011/health; echo
curl -sk -m 8 https://127.0.0.1:8013/health; echo
curl -sk -m 8 https://127.0.0.1:8014/health; echo
curl -sf http://127.0.0.1:18011/api/erp/catalog | python3 -c 'import sys,json; d=json.load(sys.stdin); items=d.get("items") or [];
bad=[i for i in items if abs(float(i.get("floor_price",0))-float(i.get("list_price",0)))>1e-6];
print("catalog_rows",len(items),"floor_ne_list",len(bad))'
""",
        timeout=240,
    )
    smoke_py = textwrap.dedent(
        '''
import json, ssl, urllib.request, uuid
from datetime import datetime, timezone
ctx = ssl._create_unverified_context()

def now():
    return datetime.now(timezone.utc).isoformat()

def rpc(port, schema, payload):
    tid = "live-" + uuid.uuid4().hex[:8]
    envelope = {
        "schema_type": schema,
        "schema_version": "1.0",
        "business_id": "biz-" + tid,
        "payload": payload,
    }
    body = {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": tid,
        "params": {
            "command": {
                "type": "task-command",
                "id": "cmd-" + tid,
                "sentAt": now(),
                "senderRole": "leader",
                "senderId": "buyer-a-local-aic",
                "sessionId": "sess-" + tid,
                "taskId": tid,
                "command": "start",
                "dataItems": [{"type": "data", "data": envelope}],
            }
        },
    }
    req = urllib.request.Request(
        "https://127.0.0.1:%d/rpc" % port,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        data = json.loads(r.read().decode())
    products = ((data.get("result") or {}).get("products") or [])
    if not products:
        return {}
    items = products[0].get("dataItems") or []
    if not items:
        return {}
    return (items[0].get("data") or {}).get("payload") or {}

base = {
    "purchase_request_id": "pr-live",
    "quantity": 100,
    "product_name": "RM-CASTER-300",
    "sku": "RM-CASTER-300",
    "specifications": {"sku": "RM-CASTER-300"},
    "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
    "need_freight": False,
}
q = rpc(8011, "agentlink.quote_request", base)
q5 = rpc(8011, "agentlink.quote_request", dict(base, quantity=500, purchase_request_id="pr-live-500"))
b = rpc(8011, "agentlink.bargain_round", dict(base, previous_unit_price=20, goal_text="优化综合成本"))
qb = rpc(8013, "agentlink.quote_request", {
    "purchase_request_id": "pr-b",
    "quantity": 200,
    "product_name": "RM-FABRIC-PRO",
    "sku": "RM-FABRIC-PRO",
    "specifications": {"sku": "RM-FABRIC-PRO", "material": "steel", "color": "black"},
    "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
    "need_freight": False,
})
qc = rpc(8014, "agentlink.quote_request", {
    "purchase_request_id": "pr-c",
    "quantity": 50,
    "product_name": "RM-TUBE-STEEL",
    "sku": "RM-TUBE-STEEL",
    "specifications": {"sku": "RM-TUBE-STEEL"},
    "destination": {"province": "浙江", "postal_code": "310000", "city": "杭州"},
    "need_freight": False,
})
print("A100", q.get("unit_price"), q.get("pricing_mode"), q.get("runtime"))
print("A500", q5.get("unit_price"), q5.get("bargain_room"), q5.get("pricing_mode"))
print("A_bargain", b.get("unit_price"), b.get("pricing_mode"))
print("B200", qb.get("unit_price"), qb.get("pricing_mode"), qb.get("runtime"))
print("C50", qc.get("unit_price"), qc.get("pricing_mode"), qc.get("runtime"))
ok = (
    float(q.get("unit_price") or -1) == 20.0
    and float(q5.get("unit_price") or -1) == 18.0
    and float(b.get("unit_price") or -1) == 20.0
    and float(qb.get("unit_price") or -1) == 35.0
    and float(qc.get("unit_price") or -1) == 100.0
    and q.get("pricing_mode") == "list_plus_promo_only"
)
print("LIVE_PASS" if ok else "LIVE_FAIL")
'''
    )
    remote_smoke = "/tmp/smoke_nofloor_live.py"
    with SCPClient(c.get_transport()) as scp:
        local_tmp = ROOT / "scripts" / "_tmp_smoke_nofloor_live.py"
        local_tmp.write_text(smoke_py, encoding="utf-8")
        scp.put(str(local_tmp), remote_smoke)
    out = run(c, f"python3 {remote_smoke}", timeout=120)
    c.close()
    if "LIVE_PASS" not in out:
        raise SystemExit("Aliyun live smoke failed")


def main() -> int:
    for name, path in JARS:
        if not path.is_file():
            print("missing", path, file=sys.stderr)
            return 2
        print("jar_ok", name, path.stat().st_size, flush=True)
    deploy_tencent()
    deploy_aliyun()
    print("GO_LIVE_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
