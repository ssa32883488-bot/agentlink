# -*- coding: utf-8 -*-
"""Diagnose RFQ failures + platform ADP for new AICs."""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


def ssh(host: str, *, key: bool) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = {
        "hostname": host,
        "username": "root",
        "timeout": 50,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if key:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def main() -> None:
    print("==== TENCENT diag ====", flush=True)
    c = ssh("81.70.46.119", key=True)
    print(
        run(
            c,
            r"""
set +e
grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_|ACPS_|AIP_|PLATFORM).*' /opt/agentlink/.env | sed -n '1,80p'
echo '--- health local ---'
for p in 8010 8012 8015; do echo -n H:$p; curl -sk --connect-timeout 4 https://127.0.0.1:$p/health; echo; done
echo '--- peer health from buyer host ---'
for u in https://39.105.20.113:8011/health https://39.105.20.113:8013/health https://39.105.20.113:8014/health; do
  echo -n "$u -> "
  curl -sk --connect-timeout 10 -o /tmp/h.json -w '%{http_code}' "$u"; echo
  cat /tmp/h.json 2>/dev/null; echo
done
echo '--- buyer-a recent journal ---'
journalctl -u agentlink-buyer-a -n 120 --no-pager | tail -80
""",
            timeout=120,
        ),
        flush=True,
    )

    print("==== live RFQ probe ====", flush=True)
    print(
        run(
            c,
            r"""
cd /opt/agentlink && .venv/bin/python - <<'PY'
import asyncio, json, os, traceback
from commerce.env_loader import load_dotenv
load_dotenv()

async def main():
    from commerce.buyer_tools import service as svc
    # find send_rfq_multi
    names = [n for n in dir(svc) if 'rfq' in n.lower()]
    print('svc rfq attrs', names)
    peers = [
        {'agent_id':'supplier-a','aic':os.environ['SUPPLIER_A_AIC'],'endpoint':'https://39.105.20.113:8011'},
        {'agent_id':'supplier-b','aic':os.environ['SUPPLIER_B_AIC'],'endpoint':'https://39.105.20.113:8013'},
        {'agent_id':'supplier-c','aic':os.environ['SUPPLIER_C_AIC'],'endpoint':'https://39.105.20.113:8014'},
    ]
    req = {
        'product_name': '高档座椅面料',
        'quantity': 300,
        'unit': '套',
        'requirements': '并行询价诊断',
    }
    # try common entrypoints
    for fn_name in ['send_rfq_multi','tool_send_rfq_multi','rfq_multi']:
        fn = getattr(svc, fn_name, None)
        if callable(fn):
            print('calling', fn_name)
            try:
                if asyncio.iscoroutinefunction(fn):
                    out = await fn(req, peers) if False else await fn(**{**req, 'candidates': peers})
                else:
                    out = fn(**{**req, 'candidates': peers})
                print(json.dumps(out, ensure_ascii=False, indent=2, default=str)[:4000])
            except TypeError as e:
                print('typeerr', e)
                try:
                    out = await fn(product_name=req['product_name'], quantity=req['quantity'], suppliers=peers)
                    print(json.dumps(out, ensure_ascii=False, indent=2, default=str)[:4000])
                except Exception:
                    traceback.print_exc()
            except Exception:
                traceback.print_exc()
            return
    # fallback: inspect schemas / low-level aip
    from commerce import discovery
    print('discovering...')
    try:
        out = await discovery.discover_suppliers(query='座椅面料', limit=8)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str)[:5000])
    except Exception:
        traceback.print_exc()

asyncio.run(main())
PY
""",
            timeout=180,
        ),
        flush=True,
    )
    c.close()

    print("==== ALIYUN supplier aip/certs ====", flush=True)
    c2 = ssh("39.105.20.113", key=False)
    print(
        run(
            c2,
            r"""
set +e
grep -E '^(SUPPLIER_|AIP_|TLS_|PLATFORM|AGENT).*' /opt/agentlink/.env | head -60
echo '--- units ---'
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for p in 8011 8013 8014; do echo -n H:$p; curl -sk https://127.0.0.1:$p/health; echo; done
echo '--- cert subject ---'
for d in supplier-a supplier-b supplier-c; do
  f=/opt/agentlink/certs/platform/$d/server-cert.pem
  [ -f "$f" ] || f=/etc/agentlink/tls/$d/server.crt
  echo "== $d $f =="
  openssl x509 -in "$f" -noout -subject -ext subjectAltName 2>/dev/null | head -5
done
echo '--- recent supplier-a log ---'
journalctl -u agentlink-supplier-a -n 40 --no-pager | tail -40
""",
            timeout=90,
        ),
        flush=True,
    )
    c2.close()


if __name__ == "__main__":
    main()
