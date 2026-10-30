# -*- coding: utf-8 -*-
"""热修：真实梧桐 ADP + 面料改写；配置 ACPS_DISCOVERY_URL 并验收。"""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce_v2/buyer_path_normal.py",
    "commerce_v2/protocol_bridge.py",
    "commerce/discovery.py",
]


def connect(role: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if role == "buyer":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect(
            "81.70.46.119",
            username="root",
            pkey=key,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    else:
        c.connect(
            "39.105.20.113",
            username="root",
            password=PW,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str) -> str:
    print("$", cmd[:160], flush=True)
    _i, o, _e = c.exec_command(cmd, timeout=240, get_pty=True)
    text = o.read().decode("utf-8", errors="replace")
    print(text[-3000:], flush=True)
    return text


def upsert_env(c: paramiko.SSHClient, key: str, val: str) -> None:
    run(
        c,
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"key, val = {key!r}, {val!r}\n"
        "p = Path('/opt/agentlink/.env')\n"
        "lines = p.read_text(encoding='utf-8').splitlines() if p.exists() else []\n"
        "out, found = [], False\n"
        "for ln in lines:\n"
        "    if ln.startswith(key + '='):\n"
        "        out.append(f'{key}={val}'); found = True\n"
        "    else:\n"
        "        out.append(ln)\n"
        "if not found:\n"
        "    out.append(f'{key}={val}')\n"
        "p.write_text('\\n'.join(out) + '\\n', encoding='utf-8')\n"
        "print('upsert', key, val)\n"
        "PY",
    )


def main() -> None:
    print("==== buyer wutong discovery ====", flush=True)
    c = connect("buyer")
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            run(c, f"mkdir -p $(dirname {remote})")
            print("put", rel, flush=True)
            scp.put(str(ROOT / rel), remote)
            run(c, f"cp -f {remote} /opt/agentlink_bundle/agentlink/{rel} 2>/dev/null || true")
    upsert_env(c, "ACPS_DISCOVERY_URL", "https://wt.ioa.pub/discovery")
    upsert_env(c, "V2_DISCOVERY_MODE", "auto")
    upsert_env(c, "ADP_DISCOVER_CACHE_TTL", "30")
    run(
        c,
        "systemctl restart agentlink-buyer-a agentlink-buyer-b; "
        "sleep 3; systemctl is-active agentlink-buyer-a agentlink-buyer-b",
    )
    # verify rewrite + ADP on server
    run(
        c,
        r"""python3 - <<'PY'
import asyncio, json, os, ssl, urllib.request
os.chdir('/opt/agentlink')
import sys
sys.path.insert(0, '/opt/agentlink')
# env from file
for ln in open('/opt/agentlink/.env', encoding='utf-8'):
    ln=ln.strip()
    if not ln or ln.startswith('#') or '=' not in ln: continue
    k,v=ln.split('=',1)
    os.environ.setdefault(k,v)
print('ACPS_DISCOVERY_URL=', os.getenv('ACPS_DISCOVERY_URL'))
from commerce_v2.buyer_path_normal import rewrite_demand
from commerce_v2.protocol_bridge import discover_suppliers
brief = rewrite_demand('帮我采购300面料', 'buyer-a')
print('REWRITE', brief)
assert '面料' in brief['rewritten_query'] or 'FABRIC' in brief['sku'], brief
assert brief['sku'].startswith('RM-FABRIC'), brief

async def go():
    disc = await discover_suppliers(brief['rewritten_query'], sku=brief['sku'], agent_id='buyer-a')
    print('DISC', disc.get('source'), 'degrade=', disc.get('degrade'), 'n=', len(disc.get('candidates') or []))
    print('ERR', disc.get('error'))
    print('META', disc.get('meta'))
    for c in (disc.get('candidates') or [])[:5]:
        print(' -', c.get('agent_id'), c.get('title'), (c.get('blurb') or '')[:50])
    assert disc.get('source') == 'platform_adp', disc
    assert any(str(c.get('agent_id'))=='supplier-b' for c in (disc.get('candidates') or [])), disc
    print('ADP_OK')
asyncio.run(go())

# HTTP chat smoke
CTX=ssl._create_unverified_context()
# new thread
body=json.dumps({'title':'面料梧桐验收'}).encode()
req=urllib.request.Request('https://127.0.0.1:8010/api/erp/chat/threads', data=body, method='POST', headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
    th=json.loads(r.read().decode())
tid=th['id']
chat=json.dumps({'text':'帮我采购300面料','thread_id':tid}).encode()
req=urllib.request.Request('https://127.0.0.1:8010/api/erp/chat', data=chat, method='POST', headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req, context=CTX, timeout=180) as r:
    out=json.loads(r.read().decode())
reply=out.get('reply') or ''
case=(out.get('case') or {})
meta=(case.get('discovery_meta') or {})
print('CHAT_SOURCE', meta.get('source'), 'degrade', meta.get('degrade'))
print('CHAT_BRIEF', (case.get('brief') or {}).get('rewritten_query'))
print('CHAT_REPLY_HEAD', reply[:180].replace('\n',' / '))
assert '脚轮' not in ((case.get('brief') or {}).get('rewritten_query') or '')
assert meta.get('source') == 'platform_adp', meta
print('CHAT_OK')
PY""",
    )
    c.close()
    print("HOTFIX_WUTONG_DONE", flush=True)


if __name__ == "__main__":
    main()
