# -*- coding: utf-8 -*-
"""Install switch script on Aliyun, cut over systemd to Java, smoke HTTPS."""
from __future__ import annotations

import json
import os
import ssl
import sys
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
HOST = "39.105.20.113"
CTX = ssl._create_unverified_context()


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        HOST,
        username="root",
        password=PW,
        timeout=45,
        allow_agent=False,
        look_for_keys=False,
    )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> str:
    print(">>>", cmd[:200], flush=True)
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    print(out[-12000:], flush=True)
    code = o.channel.recv_exit_status()
    if code != 0:
        raise SystemExit(f"remote exit {code}")
    return out


def smoke() -> bool:
    ok = True

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    for agent, port, sku, qty in (
        ("supplier-a", 8011, "RM-CASTER-300", 500),
        ("supplier-b", 8013, "RM-FABRIC-PRO", 100),
        ("supplier-c", 8014, "RM-TUBE-STEEL", 50),
    ):
        url = f"https://{HOST}:{port}"
        health = json.loads(
            urllib.request.urlopen(url + "/health", context=CTX, timeout=20).read().decode()
        )
        print("HEALTH", agent, health, flush=True)
        if health.get("runtime") != "java":
            ok = False
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
            "jsonrpc": "2.0",
            "method": "rpc",
            "id": task_id,
            "params": {
                "command": {
                    "type": "task-command",
                    "id": f"cmd-{task_id}",
                    "sentAt": now(),
                    "senderRole": "leader",
                    "senderId": "buyer-a-local-aic",
                    "sessionId": f"sess-{task_id}",
                    "taskId": task_id,
                    "command": "start",
                    "dataItems": [{"type": "data", "data": envelope}],
                }
            },
        }
        req = urllib.request.Request(
            url + "/rpc",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        data = json.loads(urllib.request.urlopen(req, context=CTX, timeout=45).read().decode())
        result = data.get("result") or {}
        state = (result.get("status") or {}).get("state")
        products = result.get("products") or []
        env = None
        if products:
            items = products[0].get("dataItems") or []
            if items:
                env = items[0].get("data")
        unit = (env or {}).get("payload", {}).get("unit_price") if env else None
        runtime = (env or {}).get("payload", {}).get("runtime") if env else None
        print("QUOTE", agent, state, unit, runtime, flush=True)
        if state != "awaiting-completion" or unit is None or runtime != "java-langchain4j":
            ok = False
        if agent == "supplier-a" and abs(float(unit) - 18.0) > 0.01:
            ok = False
    return ok


def main() -> int:
    c = connect()
    with SCPClient(c.get_transport()) as scp:
        scp.put(
            str(ROOT / "scripts" / "_remote_switch_java_suppliers.sh"),
            "/tmp/_remote_switch_java_suppliers.sh",
        )
    run(
        c,
        "sed -i 's/\\r$//' /tmp/_remote_switch_java_suppliers.sh; "
        "chmod +x /tmp/_remote_switch_java_suppliers.sh; "
        "bash /tmp/_remote_switch_java_suppliers.sh",
        timeout=180,
    )
    c.close()
    ok = smoke()
    print("PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
