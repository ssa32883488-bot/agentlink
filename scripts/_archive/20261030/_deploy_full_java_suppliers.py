# -*- coding: utf-8 -*-
"""全量上线：腾讯云采购/物流(Python) + 阿里云供应 A/B/C 用 Java 栈直接覆盖。"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
BUYER_HOST = "81.70.46.119"
SUPPLIER_HOST = "39.105.20.113"

BUYER_FILES = [
    "commerce/seat_catalog.py",
    "commerce/seed.py",
    "commerce/merchant_profiles.yaml",
    "commerce/scheme_planner.py",
    "agents/logistics/policy.yaml",
    "agents/logistics/graph.py",
    "agents/buyer_a/policy.yaml",
    "agents/buyer_b/policy.yaml",
    "agents/supplier_a/policy.yaml",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_c/policy.yaml",
    "agents/supplier_a/pricing.py",
    "agents/supplier_a/graph.py",
    "agents/supplier_b/graph.py",
    "agents/supplier_c/graph.py",
    "agents/supplier_common/promo.py",
    "agents/supplier_common/catalog_price.py",
    "agents/supplier_common/negotiate.py",
    "agents/supplier_common/freight.py",
    "docs/current_tech_stack.md",
    "docs/decision_logistics_ai_and_java_suppliers.md",
    "docs/six_agents_tech_stack_and_params.md",
    "docs/supplier_profiles_and_promotions.md",
]

JARS = [
    ("supplier-a", "java-suppliers/supplier-a/build/libs/supplier-a-0.1.0.jar"),
    ("supplier-b", "java-suppliers/supplier-b/build/libs/supplier-b-0.1.0.jar"),
    ("supplier-c", "java-suppliers/supplier-c/build/libs/supplier-c-0.1.0.jar"),
]


def connect(host: str, *, password: str | None = None) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        c.connect(
            host,
            username="root",
            password=password,
            timeout=45,
            allow_agent=False,
            look_for_keys=False,
        )
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


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 600) -> str:
    print(f"$ {cmd[:180]}{'...' if len(cmd) > 180 else ''}", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    if out.strip():
        print(out[-6000:], flush=True)
    return out


def put_rel(c: paramiko.SSHClient, rel: str, remote: str | None = None) -> None:
    local = ROOT / rel
    if not local.is_file():
        print("skip missing", rel, flush=True)
        return
    remote = remote or f"/opt/agentlink/{rel.replace(chr(92), '/')}"
    parent = remote.rsplit("/", 1)[0]
    run(c, f"mkdir -p {parent}")
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(local), remote)
    print("put", rel, "->", remote, flush=True)


def deploy_buyer() -> None:
    print("==== Tencent buyer/logistics ====", flush=True)
    c = connect(BUYER_HOST)
    for rel in BUYER_FILES:
        put_rel(c, rel)
    run(
        c,
        """
set -e
cd /opt/agentlink
/opt/agentlink/.venv/bin/python -m commerce.seed || true
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics || true
sleep 3
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
curl -sk https://127.0.0.1:8015/health || curl -s http://127.0.0.1:8015/health || true
""",
    )
    c.close()


def deploy_java_suppliers() -> None:
    print("==== Aliyun Java suppliers (overwrite) ====", flush=True)
    for _, rel in JARS:
        if not (ROOT / rel).is_file():
            raise SystemExit(f"missing jar {rel}; build first")

    c = connect(SUPPLIER_HOST, password=PW)
    run(c, "mkdir -p /opt/agentlink/java-suppliers /var/log/agentlink")

    # JDK 17 (Alibaba Cloud Linux / RHEL → dnf|yum；Debian → apt)
    run(
        c,
        r"""
set -e
if ! command -v java >/dev/null 2>&1 || ! java -version 2>&1 | grep -q '17'; then
  if command -v dnf >/dev/null; then
    dnf install -y java-17-openjdk-headless || dnf install -y java-17-openjdk
  elif command -v yum >/dev/null; then
    yum install -y java-17-openjdk-headless || yum install -y java-17-openjdk
  elif command -v apt-get >/dev/null; then
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y openjdk-17-jre-headless || true
  fi
fi
java -version
which java
""",
        timeout=400,
    )

    for name, rel in JARS:
        put_rel(c, rel, f"/opt/agentlink/java-suppliers/{name}.jar")

    # Rewrite systemd units to Java + existing TLS
    run(
        c,
        r"""
set -e
# pick TLS files
if [ -f /etc/agentlink/tls/fullchain.pem ] && [ -f /etc/agentlink/tls/privkey.pem ]; then
  CRT=/etc/agentlink/tls/fullchain.pem
  KEY=/etc/agentlink/tls/privkey.pem
elif [ -f /etc/agentlink/tls/server.crt ] && [ -f /etc/agentlink/tls/server.key ]; then
  CRT=/etc/agentlink/tls/server.crt
  KEY=/etc/agentlink/tls/server.key
else
  echo 'NO_TLS'; exit 1
fi
echo "TLS=$CRT"

JAVA_BIN=$(command -v java)
[ -n "$JAVA_BIN" ] || { echo 'java missing'; exit 1; }

write_java_unit() {
  local name="$1" port="$2" aic_env="$3"
  cat > "/etc/systemd/system/agentlink-${name}.service" <<EOF
[Unit]
Description=AgentLink ${name} (Java HTTPS)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/agentlink
Environment=AIP_IDENTITY_BINDING=0
Environment=AIP_SSL_INSECURE=1
Environment=PORT=${port}
Environment=SSL_ENABLED=true
Environment=SSL_CERT=file:${CRT}
Environment=SSL_KEY=file:${KEY}
EnvironmentFile=-/opt/agentlink/.env
EnvironmentFile=-/etc/agentlink/${name}.env
ExecStart=${JAVA_BIN} -jar /opt/agentlink/java-suppliers/${name}.jar
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/${name}.log
StandardError=append:/var/log/agentlink/${name}.log

[Install]
WantedBy=multi-user.target
EOF
}

# stop old python suppliers first
systemctl stop agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c || true

write_java_unit supplier-a 8011 SUPPLIER_A_AIC
write_java_unit supplier-b 8013 SUPPLIER_B_AIC
write_java_unit supplier-c 8014 SUPPLIER_C_AIC

systemctl daemon-reload
systemctl enable agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
sleep 8
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
echo '--- health ---'
curl -sk https://127.0.0.1:8011/health; echo
curl -sk https://127.0.0.1:8013/health; echo
curl -sk https://127.0.0.1:8014/health; echo
echo '--- recent logs a ---'
tail -n 30 /var/log/agentlink/supplier-a.log || journalctl -u agentlink-supplier-a -n 30 --no-pager || true
""",
        timeout=180,
    )
    c.close()


def smoke_remote_suppliers() -> None:
    print("==== remote smoke quote ====", flush=True)
    c = connect(SUPPLIER_HOST, password=PW)
    # upload smoke helper and run against localhost https
    put_rel(c, "scripts/smoke_java_suppliers.py", "/opt/agentlink/scripts/smoke_java_suppliers.py")
    run(
        c,
        r"""
set -e
cd /opt/agentlink
# rewrite smoke targets to https localhost
python3 - <<'PY'
import json, uuid, urllib.request, ssl
from datetime import datetime, timezone

CTX = ssl._create_unverified_context()

def now():
    return datetime.now(timezone.utc).isoformat()

TARGETS = (
    ("supplier-a", "https://127.0.0.1:8011/rpc", "RM-CASTER-300", 500),
    ("supplier-b", "https://127.0.0.1:8013/rpc", "RM-FABRIC-PRO", 100),
    ("supplier-c", "https://127.0.0.1:8014/rpc", "RM-TUBE-STEEL", 50),
)
ok = True
for agent, url, sku, qty in TARGETS:
    # health
    h = urllib.request.urlopen(url.replace('/rpc','/health'), context=CTX, timeout=10)
    health = json.loads(h.read().decode())
    print('HEALTH', agent, health)
    if health.get('runtime') != 'java':
        print('FAIL runtime', agent); ok=False
    task_id = f"smoke-{uuid.uuid4().hex[:8]}"
    envelope = {
        "schema_type": "agentlink.quote_request",
        "schema_version": "1.0",
        "business_id": f"biz-{task_id}",
        "payload": {
            "purchase_request_id": f"pr-{task_id}",
            "quantity": qty,
            "product_name": sku,
            "sku": sku,
            "specifications": {"sku": sku, "material": "demo", "color": "black"},
            "dest_province": "河北",
            "need_freight": False,
        },
    }
    body = {
        "jsonrpc": "2.0", "method": "rpc", "id": task_id,
        "params": {"command": {
            "type": "task-command", "id": f"cmd-{task_id}", "sentAt": now(),
            "senderRole": "leader", "senderId": "buyer-a-local-aic",
            "sessionId": f"sess-{task_id}", "taskId": task_id, "command": "start",
            "dataItems": [{"type": "data", "data": envelope}],
        }},
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    data = json.loads(urllib.request.urlopen(req, context=CTX, timeout=30).read().decode())
    result = data.get("result") or {}
    state = (result.get("status") or {}).get("state")
    products = result.get("products") or []
    env = None
    if products:
        items = products[0].get("dataItems") or []
        if items: env = items[0].get("data")
    unit = (env or {}).get("payload", {}).get("unit_price") if env else None
    print('QUOTE', agent, state, unit)
    if state != 'awaiting-completion' or unit is None:
        ok = False
    if agent == 'supplier-a' and abs(float(unit)-18.0)>0.01:
        print('FAIL caster discount', unit); ok=False
print('PASS' if ok else 'FAIL')
raise SystemExit(0 if ok else 1)
PY
""",
        timeout=120,
    )
    c.close()


def main() -> int:
    deploy_buyer()
    deploy_java_suppliers()
    smoke_remote_suppliers()
    print("DEPLOY_FULL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
