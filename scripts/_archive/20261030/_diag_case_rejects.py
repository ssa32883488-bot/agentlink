# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
CID = "case-7d77f9af"


def main() -> None:
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
    cmd = r"""
cd /opt/agentlink && .venv/bin/python - <<'PY'
import json, os
from pathlib import Path

cid = 'case-7d77f9af'
# load buyer-b cases
p = Path('data/procurement_cases_buyer-b.json')
print('path', p, 'exists', p.is_file())
raw = p.read_text(encoding='utf-8') if p.is_file() else '{}'
data = json.loads(raw)
print('top_type', type(data).__name__)
if isinstance(data, dict):
    print('top_keys', list(data.keys())[:20])
    sample = next(iter(data.values())) if data else None
    print('sample_type', type(sample).__name__, str(sample)[:200] if sample is not None else None)
case = None
if isinstance(data, list):
    for it in data:
        if isinstance(it, dict) and it.get('case_id') == cid:
            case = it
            break
elif isinstance(data, dict):
    if cid in data and isinstance(data[cid], dict):
        case = data[cid]
    elif 'cases' in data and isinstance(data['cases'], list):
        for it in data['cases']:
            if isinstance(it, dict) and it.get('case_id') == cid:
                case = it
                break
    else:
        for v in data.values():
            if isinstance(v, dict) and v.get('case_id') == cid:
                case = v
                break
            if isinstance(v, str) and cid in v:
                print('found cid inside string value, len', len(v))
print('case_found', bool(case))
if case:
    print('brief', json.dumps(case.get('brief'), ensure_ascii=False))
    print('state', case.get('state'))
    print('keys', sorted(case.keys())[:40])
    for k in ('quotes', 'rfq_batch', 'last_rfq_batch', 'candidates', 'shortlist', 'rfq_results'):
        v = case.get(k)
        if v is not None:
            print('---', k, '---')
            print(json.dumps(v, ensure_ascii=False, default=str)[:3000])
# also grep file for cid snippet
idx = raw.find(cid)
print('idx', idx)
if idx >= 0:
    print('snippet', raw[max(0, idx-200):idx+800])

# interactions log
for ip in Path('data').rglob('*.jsonl'):
    if 'interaction' in ip.name or 'amp' in ip.name or 'aip' in ip.name:
        print('logfile', ip)
hits = []
for ip in Path('.').rglob('*.jsonl'):
    try:
        text = ip.read_text(encoding='utf-8', errors='replace')
    except Exception:
        continue
    if cid in text or '7d77f9af' in text or '7555e73' in text:
        print('hitfile', ip)
        for line in text.splitlines()[-200:]:
            if '7d77f9af' in line or '7555e73' in line or '70b6b9d' in line or '3e7f487' in line or 'rejected' in line.lower():
                if 'RM-' in line or 'reject' in line.lower() or 'product_name' in line or '7d77' in line:
                    hits.append(line[:500])
print('hits', len(hits))
for h in hits[-15:]:
    print(h)

# reproduce normalize
from agents.supplier_common.catalog_price import requested_sku, quote_from_catalog
import yaml
brief = (case or {}).get('brief') or {}
pname = brief.get('product_name')
print('requested_sku', requested_sku(product_name=pname, sku=None, specifications=brief.get('specifications')))
for name in ('supplier_a','supplier_b','supplier_c'):
    pol = yaml.safe_load(Path(f'agents/{name}/policy.yaml').read_text(encoding='utf-8'))
    q = quote_from_catalog(pol, int(brief.get('quantity') or 1), product_name=pname, specifications=brief.get('specifications') or {})
    print(name, {k:q.get(k) for k in ('catalog_hit','sku','unit_price','reject_reason','requested_sku')})
PY
"""
    _, o, e = c.exec_command(cmd, timeout=90, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()


if __name__ == "__main__":
    main()
