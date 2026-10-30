# -*- coding: utf-8 -*-
"""Build+deploy Java suppliers (初询不泄优惠 / 议价才披露) + buyer mapping; smoke."""
from __future__ import annotations

import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "java-suppliers"
HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
GRADLE = JS / ".tools" / "gradle-8.10.2" / "bin" / "gradle.bat"

JAR_MAP = {
    "supplier-a/build/libs/supplier-a-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-a.jar",
    "supplier-b/build/libs/supplier-b-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-b.jar",
    "supplier-c/build/libs/supplier-c-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-c.jar",
}

BUYER_FILES = [
    "commerce/buyer_tools/service.py",
    "commerce/chat_buyer_wit.py",
    "commerce/flow_service.py",
    "agents/supplier_common/negotiate.py",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build() -> None:
    cmd = [
        str(GRADLE),
        ":supplier-a:bootJar",
        ":supplier-b:bootJar",
        ":supplier-c:bootJar",
        "-q",
    ]
    print("BUILD", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(JS))


def rpc(url: str, schema: str, payload: dict) -> dict:
    task_id = f"smoke-{uuid.uuid4().hex[:8]}"
    envelope = {
        "schema_type": schema,
        "schema_version": "1.0",
        "business_id": f"biz-{task_id}",
        "payload": payload,
    }
    body = {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": task_id,
        "params": {
            "command": {
                "type": "task-command",
                "id": f"cmd-{task_id}",
                "sentAt": _now(),
                "senderRole": "leader",
                "senderId": "buyer-a-local-aic",
                "sessionId": f"sess-{task_id}",
                "taskId": task_id,
                "command": "start",
                "dataItems": [{"type": "data", "data": envelope}],
            }
        },
    }
    r = httpx.post(url, json=body, timeout=60.0, verify=False)
    r.raise_for_status()
    return r.json()


def extract_payload(data: dict) -> dict:
    result = data.get("result") or {}
    products = result.get("products") or []
    if not products:
        return {}
    items = products[0].get("dataItems") or []
    if not items:
        return {}
    env = items[0].get("data") or {}
    return env.get("payload") or {}


def deploy_jars() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    with SCPClient(c.get_transport()) as scp:
        for local, remote in JAR_MAP.items():
            p = JS / local
            scp.put(str(p), remote)
            print("put", p.name, p.stat().st_size, flush=True)
    _, o, e = c.exec_command(
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "sleep 45; systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "curl -sk -m 10 https://127.0.0.1:8011/health; echo",
        timeout=120,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()


def deploy_buyer() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = c.open_sftp()
    for rel in BUYER_FILES:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put buyer", rel, flush=True)
    sftp.close()
    _, o, e = c.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 4; systemctl is-active agentlink-buyer-a",
        timeout=60,
        get_pty=True,
    )
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    c.close()


def smoke() -> int:
    base = f"https://{HOST}"
    payload = {
        "purchase_request_id": "pr-phase",
        "quantity": 300,
        "product_name": "重型脚轮",
        "sku": "RM-CASTER-300",
        "specifications": {"sku": "RM-CASTER-300"},
        "destination": {"province": "河北", "postal_code": "071000", "city": "保定"},
        "need_freight": False,
    }
    q = extract_payload(rpc(f"{base}:8011/rpc", "agentlink.quote_request", payload))
    print(
        "initial",
        {
            k: q.get(k)
            for k in (
                "unit_price",
                "pricing_mode",
                "promotions_disclosed",
                "policy_hints",
                "promo_preview",
                "note",
            )
        },
        flush=True,
    )
    q500 = extract_payload(
        rpc(
            f"{base}:8011/rpc",
            "agentlink.quote_request",
            {**payload, "quantity": 500, "purchase_request_id": "pr-phase-500"},
        )
    )
    print(
        "initial500",
        {k: q500.get(k) for k in ("unit_price", "pricing_mode", "promotions_disclosed", "policy_hints")},
        flush=True,
    )
    b = extract_payload(
        rpc(
            f"{base}:8011/rpc",
            "agentlink.bargain_round",
            {
                **payload,
                "previous_unit_price": 20,
                "goal_text": "请问有没有价格优惠？",
                "need_freight": False,
            },
        )
    )
    pol = b.get("policy") if isinstance(b.get("policy"), dict) else {}
    print(
        "bargain",
        {
            "unit_price": b.get("unit_price"),
            "promotions_disclosed": b.get("promotions_disclosed"),
            "hints": (pol.get("hints") or b.get("policy_hints") or [])[:1],
            "reach": pol.get("reach_example") or b.get("reach_promo_preview"),
            "talk": (b.get("talk_track") or "")[:60],
        },
        flush=True,
    )

    ok = True
    if float(q.get("unit_price") or -1) != 20.0:
        print("FAIL initial unit", q.get("unit_price"))
        ok = False
    if q.get("promotions_disclosed") is not False:
        print("FAIL initial should hide promo", q.get("promotions_disclosed"))
        ok = False
    if q.get("policy_hints") not in (None, [], {}):
        print("FAIL initial leaked policy_hints", q.get("policy_hints"))
        ok = False
    if float(q500.get("unit_price") or -1) != 20.0:
        print("FAIL initial@500 must stay list price", q500.get("unit_price"))
        ok = False
    if float(b.get("unit_price") or -1) != 20.0:
        print("FAIL bargain must not cut list", b.get("unit_price"))
        ok = False
    if not (pol.get("hints") or b.get("policy_hints")):
        print("FAIL bargain missing hints", pol)
        ok = False
    reach = pol.get("reach_example") or b.get("reach_promo_preview") or {}
    if float((reach or {}).get("goods_after_promo") or 0) != 9000.0:
        print("FAIL reach after promo", reach)
        ok = False
    print("PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


def main() -> int:
    build()
    deploy_jars()
    deploy_buyer()
    return smoke()


if __name__ == "__main__":
    raise SystemExit(main())
