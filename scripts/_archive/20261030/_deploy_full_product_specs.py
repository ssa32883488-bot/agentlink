# -*- coding: utf-8 -*-
"""Deploy full product specs (weight/volume) for quotes + shipping derive."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

BUYER_FILES = [
    "commerce/seat_catalog.py",
    "commerce/flow_service.py",
    "commerce/chat_buyer_wit.py",
    "commerce/buyer_tools/service.py",
    "agents/buyer_a/graph.py",
    "agents/supplier_common/catalog_price.py",
    "agents/supplier_common/negotiate.py",
    "agents/logistics/graph.py",
]

SUPPLIER_FILES = [
    "commerce/seat_catalog.py",
    "agents/supplier_common/catalog_price.py",
    "agents/supplier_common/negotiate.py",
    "agents/supplier_a/graph.py",
    "agents/supplier_b/graph.py",
    "agents/supplier_c/graph.py",
]


def put(c: paramiko.SSHClient, files: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in files:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    out = o.read() + e.read()
    sys.stdout.buffer.write(out + b"\n")
    return out.decode("utf-8", "replace")


def main() -> None:
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        BUYER,
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put(b, BUYER_FILES)
    run(
        b,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
        "sleep 3; systemctl is-active agentlink-buyer-a agentlink-logistics; "
        "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
        "from commerce.seat_catalog import product_physical_specs, estimate_weight_kg\n"
        "from agents.supplier_common.catalog_price import quote_from_catalog\n"
        "from agents.supplier_common.negotiate import enrich_initial_quote\n"
        "p=product_physical_specs('RM-CASTER-300', qty=500)\n"
        "assert p['weight_kg']==200.0, p\n"
        "assert p['volume_m3']==2.5, p\n"
        "policy={'catalog':[{'sku':'RM-CASTER-300','name':'重型脚轮','unit_price':18,'available_quantity':9999,'lead_time_days':5,'moq':1}],'default_tax_included':True}\n"
        "priced=quote_from_catalog(policy,500,product_name='重型脚轮',sku='RM-CASTER-300')\n"
        "assert priced['weight_kg']==200.0, priced\n"
        "q={'unit_price':18,'product':{'sku':'RM-CASTER-300','name':'重型脚轮','quantity':500}}\n"
        "q=enrich_initial_quote(q, policy, rfq_payload={'quantity':500}, priced=priced)\n"
        "assert q['product']['weight_kg']==200.0, q['product']\n"
        "assert q['product']['volume_m3']==2.5, q['product']\n"
        "print('UNIT_SPECS_OK', q['product']['weight_kg'], q['product']['volume_m3'])\n"
        "PY",
    )
    # cert CN check vs LOGISTICS_AIC
    run(
        b,
        "echo CERT_CN=; openssl x509 -in /opt/agentlink/certs/platform/logistics/agent-cert.pem -noout -subject 2>/dev/null | head -1; "
        "echo ENV_AIC=; grep LOGISTICS_AIC /opt/agentlink/.env",
    )
    b.close()

    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put(s, SUPPLIER_FILES)
    run(
        s,
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
        "sleep 3; systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c",
    )
    s.close()
    print("DEPLOY_FULL_PRODUCT_SPECS_DONE", flush=True)


if __name__ == "__main__":
    main()
