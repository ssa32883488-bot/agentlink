# -*- coding: utf-8 -*-
"""打通并上线三家供应：对话库存/价目/询价箱/待办 + policy/seed/UI，冒烟 A/B/C。"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER_HOST = "81.70.46.119"

FILES = [
    "commerce/chat_supplier.py",
    "commerce/supplier_routes.py",
    "commerce/supplier_service.py",
    "commerce/seat_catalog.py",
    "commerce/seed.py",
    "commerce/scheme_planner.py",
    "agents/supplier_a/policy.yaml",
    "agents/supplier_b/policy.yaml",
    "agents/supplier_c/policy.yaml",
    "agents/supplier_common/promo.py",
    "agents/supplier_common/negotiate.py",
    "agents/supplier_common/catalog_price.py",
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


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 240) -> str:
    print(f"$ {cmd[:140]}...", flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    sys.stdout.buffer.write((out[-6000:] + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    return out


def put_files(c: paramiko.SSHClient, rels: list[str]) -> None:
    with SCPClient(c.get_transport()) as scp:
        for rel in rels:
            local = ROOT / rel
            if not local.is_file():
                print("skip", rel, flush=True)
                continue
            remote = f"/opt/agentlink/{rel.replace(chr(92), '/')}"
            run(c, f"mkdir -p {remote.rsplit('/', 1)[0]}", timeout=15)
            scp.put(str(local), remote)
            print("put", rel, flush=True)


def put_jars(c: paramiko.SSHClient) -> None:
    run(c, "mkdir -p /opt/agentlink/java-suppliers", timeout=15)
    with SCPClient(c.get_transport()) as scp:
        for name, path in JARS:
            if not path.is_file():
                print("WARN missing jar", path, flush=True)
                continue
            scp.put(str(path), f"/opt/agentlink/java-suppliers/{name}.jar")
            print("put jar", name, path.stat().st_size, flush=True)


def main() -> int:
    # --- Aliyun suppliers ---
    print("==== Aliyun A/B/C ====", flush=True)
    c = connect(HOST, password=PW)
    put_files(c, FILES)
    put_jars(c)

    smoke = textwrap.dedent(
        '''
import json, urllib.request

def chat(port, text):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/erp/chat" % port,
        data=json.dumps({"text": text}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def via_ui(ui_port, agent, text):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/proxy/%s/api/erp/chat" % (ui_port, agent),
        data=json.dumps({"text": text}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

ok = True
for agent, erp, ui in (
    ("supplier-a", 18011, 8091),
    ("supplier-b", 18013, 8093),
    ("supplier-c", 18014, 8094),
):
    o = chat(erp, "查看库存")
    reply = o.get("reply") or ""
    intent = o.get("intent")
    good = intent == "query_catalog" and "RM-" in reply and not reply.startswith("我是供应商助手")
    print(agent, "erp", "OK" if good else "BAD", intent, "lines", reply.count("RM-"))
    ok = ok and good
    u = via_ui(ui, agent, "价目")
    ugood = (u.get("intent") == "query_catalog") and ("RM-" in (u.get("reply") or ""))
    print(agent, "ui", "OK" if ugood else "BAD", u.get("intent"))
    ok = ok and ugood
print("ALL_SUPPLIERS_CHAT_PASS" if ok else "ALL_SUPPLIERS_CHAT_FAIL")
'''
    )
    tmp = ROOT / "scripts" / "_tmp_smoke_all_sup_chat.py"
    tmp.write_text(smoke, encoding="utf-8")
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(tmp), "/tmp/smoke_all_sup_chat.py")

    out = run(
        c,
        r"""
set -e
cd /opt/agentlink
.venv/bin/python -m commerce.seed

# ensure UI is HTTP (no ssl) for IP access
for pair in "supplier-a:8091:config_supplier_a.yaml" "supplier-b:8093:config_supplier_b.yaml" "supplier-c:8094:config_supplier_c.yaml"; do
  name=${pair%%:*}; rest=${pair#*:}; port=${rest%%:*}; cfg=${rest#*:}
  cat > /etc/systemd/system/agentlink-ui-${name}.service <<EOF
[Unit]
Description=AgentLink UI ${name}
After=network.target
[Service]
Type=simple
WorkingDirectory=/opt/agentlink
EnvironmentFile=-/opt/agentlink/.env
Environment=HOST=0.0.0.0
Environment=UI_PORT=${port}
Environment=UI_HTTPX_VERIFY=0
Environment=AGENTLINK_UI_CONFIG=/opt/agentlink/ui/${cfg}
ExecStart=/opt/agentlink/.venv/bin/python -m uvicorn ui.app:app --host 0.0.0.0 --port ${port}
Restart=on-failure
RestartSec=3
StandardOutput=append:/var/log/agentlink/ui-${name}.log
StandardError=append:/var/log/agentlink/ui-${name}.log
[Install]
WantedBy=multi-user.target
EOF
done
systemctl daemon-reload

systemctl restart \
  agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c \
  agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp \
  agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c

# wait java
for i in $(seq 1 14); do
  if curl -sk -m 4 https://127.0.0.1:8011/health | grep -q java \
     && curl -sk -m 4 https://127.0.0.1:8013/health | grep -q java \
     && curl -sk -m 4 https://127.0.0.1:8014/health | grep -q java; then
    echo java_ready_$i; break
  fi
  echo wait_java_$i; sleep 5
done

systemctl is-active \
  agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c \
  agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp \
  agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c

curl -sk https://127.0.0.1:8011/health; echo
curl -sk https://127.0.0.1:8013/health; echo
curl -sk https://127.0.0.1:8014/health; echo
curl -sS -o /dev/null -w 'uiA:%{http_code} uiB:%{http_code} uiC:%{http_code}\n' \
  http://127.0.0.1:8091/ http://127.0.0.1:8093/ http://127.0.0.1:8094/ || true

python3 /tmp/smoke_all_sup_chat.py
""",
        timeout=300,
    )
    c.close()

    # sync buyer host policies/scheme for bargain-from-promo
    print("==== Tencent sync policies/scheme ====", flush=True)
    try:
        c2 = connect(BUYER_HOST)
        put_files(
            c2,
            [
                "agents/supplier_a/policy.yaml",
                "agents/supplier_b/policy.yaml",
                "agents/supplier_c/policy.yaml",
                "agents/supplier_common/promo.py",
                "commerce/scheme_planner.py",
                "commerce/seat_catalog.py",
            ],
        )
        run(
            c2,
            "systemctl restart agentlink-buyer-a agentlink-buyer-b || true; sleep 2; systemctl is-active agentlink-buyer-a agentlink-buyer-b",
            timeout=60,
        )
        c2.close()
    except Exception as exc:  # noqa: BLE001
        print("WARN tencent:", exc, flush=True)

    if "ALL_SUPPLIERS_CHAT_PASS" not in out:
        print("GO_LIVE_SUPPLIERS_FAIL", flush=True)
        return 1
    print("GO_LIVE_SUPPLIERS_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
