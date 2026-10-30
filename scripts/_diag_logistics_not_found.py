# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(PEM))
    c.connect("81.70.46.119", username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    _i, o, e = c.exec_command(cmd, timeout=60)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def main() -> None:
    c = connect()
    print("=== tickets ===")
    print(
        run(
            c,
            "curl -sk 'https://127.0.0.1:8010/api/erp/tickets' | python3 -c '"
            "import sys,json; d=json.load(sys.stdin);\n"
            "for t in d.get(\"items\") or []:\n"
            "  print(t.get(\"ticket_id\") or t.get(\"id\"), t.get(\"kind\") or t.get(\"type\"), t.get(\"title\",\"\")[:40], t.get(\"status\"), \"lid=\", t.get(\"logistics_id\"), \"oid=\", t.get(\"order_id\"))\n"
            "'",
        )
    )
    print("=== orders/logistics dump ===")
    print(
        run(
            c,
            "cd /opt/agentlink && /opt/agentlink/.venv/bin/python - <<'PY'\n"
            "import json\n"
            "from pathlib import Path\n"
            "from commerce_v2 import order_ids\n"
            "items=order_ids.list_open_tickets('buyer-a')\n"
            "print('open tickets', len(items))\n"
            "for t in items:\n"
            "  print('T', t.get('ticket_id') or t.get('id'), t.get('kind'), t.get('title','')[:50], 'status', t.get('status'))\n"
            "  print('  keys', sorted(t.keys()))\n"
            "  print('  logistics_id', t.get('logistics_id'), 'order_id', t.get('order_id'))\n"
            "p=Path('data/v2_orders')\n"
            "print('files', list(p.glob('*')) if p.exists() else 'no dir')\n"
            "for f in sorted((p.glob('*.json') if p.exists() else []))[:8]:\n"
            "  d=json.loads(f.read_text(encoding='utf-8'))\n"
            "  if 'logistics' in f.name or 'lg-' in str(d) or isinstance(d, dict) and ('logistics' in d or any('logistics' in str(k) for k in d)):\n"
            "    print('FILE', f.name, 'top', list(d)[:12] if isinstance(d, dict) else type(d))\n"
            "# dump store structure\n"
            "store=order_ids._load() if hasattr(order_ids,'_load') else None\n"
            "if store is None:\n"
            "  # try common paths\n"
            "  for cand in [Path('data/v2_orders.json'), Path('data/v2_orders/orders.json'), *Path('data').glob('**/v2_orders*.json')]:\n"
            "    if cand.is_file():\n"
            "      print('cand', cand, 'size', cand.stat().st_size)\n"
            "      d=json.loads(cand.read_text(encoding='utf-8'))\n"
            "      print('keys', list(d)[:20] if isinstance(d, dict) else type(d))\n"
            "      if isinstance(d, dict):\n"
            "        logs=d.get('logistics') or d.get('logistics_orders') or {}\n"
            "        print('logistics n', len(logs) if isinstance(logs, dict) else logs)\n"
            "        for k,v in list((logs or {}).items())[:10]:\n"
            "          print(' L', k, (v or {}).get('title'), (v or {}).get('order_id'), (v or {}).get('buyer_ack'), (v or {}).get('logistics_ack'))\n"
            "        ords=d.get('orders') or {}\n"
            "        print('orders n', len(ords))\n"
            "        for k,v in list(ords.items())[:8]:\n"
            "          if '29fd9d01' in k or 'FABRIC' in k:\n"
            "            print(' O', k, v.get('effective'), v.get('buyer_ack'), v.get('supplier_ack'))\n"
            "PY",
        )
    )
    print("=== try ack ===")
    print(
        run(
            c,
            "curl -sk -X POST 'https://127.0.0.1:8010/api/erp/tickets' >/dev/null; "
            "TID=$(curl -sk 'https://127.0.0.1:8010/api/erp/tickets' | python3 -c 'import sys,json; items=json.load(sys.stdin).get(\"items\") or [];\n"
            "xs=[t for t in items if \"物流\" in str(t.get(\"title\") or \"\") or t.get(\"kind\")==\"logistics\" or t.get(\"logistics_id\")];\n"
            "print((xs[0].get(\"ticket_id\") or xs[0].get(\"id\") or xs[0].get(\"logistics_id\") or \"\") if xs else \"\")'); "
            "echo TID=$TID; "
            "curl -sk -X POST \"https://127.0.0.1:8010/api/erp/tickets/$TID/ack-logistics\" -H 'Content-Type: application/json' -d '{}' ; echo; "
            "curl -sk -X POST 'https://127.0.0.1:8010/api/v2/gate/ack-logistics' -H 'Content-Type: application/json' -d \"{\\\"ticket_id\\\":\\\"$TID\\\"}\" ; echo",
        )
    )
    c.close()


if __name__ == "__main__":
    main()
