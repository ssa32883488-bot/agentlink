# -*- coding: utf-8 -*-
"""Deploy supplier Wit+DeepSeek chat to Aliyun A/B/C; sync LLM env; smoke 查看库存."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
HOST = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

FILES = [
    "commerce/chat_supplier_wit.py",
    "commerce/chat_supplier.py",
    "commerce/supplier_routes.py",
    "commerce/env_loader.py",
    "commerce/choice_actions.py",
]

JARS = [
    ("supplier-a", ROOT / "java-suppliers/supplier-a/build/libs/supplier-a-0.1.0.jar"),
    ("supplier-b", ROOT / "java-suppliers/supplier-b/build/libs/supplier-b-0.1.0.jar"),
    ("supplier-c", ROOT / "java-suppliers/supplier-c/build/libs/supplier-c-0.1.0.jar"),
]


def main() -> int:
    # parse local .env llm keys
    env_path = ROOT / ".env"
    kv: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip().strip('"').strip("'")
    need = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_PROVIDER", "BUYER_CHAT_ENGINE"]
    for k in need:
        if k == "LLM_API_KEY" and not kv.get(k):
            print("missing LLM_API_KEY in local .env", flush=True)
            return 2

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PW, timeout=45, allow_agent=False, look_for_keys=False)

    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            remote = f"/opt/agentlink/{rel}"
            _, o, _ = c.exec_command(f"mkdir -p {remote.rsplit('/', 1)[0]}")
            o.channel.recv_exit_status()
            scp.put(str(ROOT / rel), remote)
            print("put", rel, flush=True)
        for name, path in JARS:
            if path.is_file():
                scp.put(str(path), f"/opt/agentlink/java-suppliers/{name}.jar")
                print("put jar", name, flush=True)
            else:
                print("skip jar", name, flush=True)

    # merge LLM into remote .env
    llm_block = "\n".join(
        [
            f"LLM_PROVIDER={kv.get('LLM_PROVIDER', 'deepseek')}",
            f"LLM_API_KEY={kv.get('LLM_API_KEY', '')}",
            f"LLM_BASE_URL={kv.get('LLM_BASE_URL', 'https://api.deepseek.com')}",
            f"LLM_MODEL={kv.get('LLM_MODEL', 'deepseek-chat')}",
            "BUYER_CHAT_ENGINE=wit",
            "SUPPLIER_CHAT_ENGINE=wit",
        ]
    )
    # write via sftp tempfile
    remote_patch = "/tmp/agentlink_llm.env.patch"
    with SCPClient(c.get_transport()) as scp:
        local_patch = ROOT / "scripts" / "_tmp_llm_patch.env"
        local_patch.write_text(llm_block + "\n", encoding="utf-8")
        scp.put(str(local_patch), remote_patch)

    _, o, e = c.exec_command(
        r"""
set -e
cd /opt/agentlink
# ensure wit package
.venv/bin/python -c 'import wit; print("wit_ok", getattr(wit, "__version__", "?"))' || .venv/bin/pip install -q wit
# merge env keys
python3 - <<'PY'
from pathlib import Path
env=Path('/opt/agentlink/.env')
text=env.read_text(encoding='utf-8') if env.exists() else ''
lines=[ln for ln in text.splitlines() if not ln.strip().startswith(('LLM_','BUYER_CHAT_ENGINE=','SUPPLIER_CHAT_ENGINE='))]
patch=Path('/tmp/agentlink_llm.env.patch').read_text(encoding='utf-8').splitlines()
# drop empty trailing
out='\n'.join([*lines, *patch]).rstrip()+'\n'
env.write_text(out, encoding='utf-8')
print('env_llm_merged')
PY
# also export into java unit env files
for name in supplier-a supplier-b supplier-c; do
  f=/etc/agentlink/${name}.env
  mkdir -p /etc/agentlink
  touch "$f"
  grep -vE '^(LLM_|BUYER_CHAT_ENGINE=|SUPPLIER_CHAT_ENGINE=)' "$f" > /tmp/${name}.env.clean || true
  cat /tmp/${name}.env.clean /tmp/agentlink_llm.env.patch > "$f"
done

systemctl restart \
  agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp \
  agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c \
  agentlink-ui-supplier-a agentlink-ui-supplier-b agentlink-ui-supplier-c
sleep 8
systemctl is-active agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp
curl -sS http://127.0.0.1:18011/api/erp/chat-engine; echo
curl -sS http://127.0.0.1:18013/api/erp/chat-engine; echo
curl -sS http://127.0.0.1:18014/api/erp/chat-engine; echo

# smoke chat (non-stream) for A/B/C — may take LLM time
python3 - <<'PY'
import json, urllib.request, time
ok=True
for agent, port in (("supplier-a",18011),("supplier-b",18013),("supplier-c",18014)):
    t0=time.time()
    req=urllib.request.Request(
        f'http://127.0.0.1:{port}/api/erp/chat',
        data=json.dumps({"text":"查看库存"}).encode(),
        headers={'content-type':'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            o=json.loads(r.read().decode())
    except Exception as exc:
        print(agent, 'ERR', exc)
        ok=False
        continue
    reply=o.get('reply') or ''
    engine=o.get('engine')
    intent=o.get('intent')
    # must be wit, not canned help
    canned = reply.startswith('我是供应商助手')
    good = engine=='wit' and (not canned) and ('RM-' in reply or '挂牌' in reply or '库存' in reply or '价目' in reply or len(reply)>20)
    print(agent, 'OK' if good else 'BAD', 'engine', engine, 'intent', intent, 'secs', round(time.time()-t0,1), 'snip', reply[:80].replace('\n',' '))
    ok = ok and good
print('SUPPLIER_WIT_PASS' if ok else 'SUPPLIER_WIT_FAIL')
PY
""",
        timeout=420,
        get_pty=True,
    )
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    sys.stdout.buffer.write((out + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    c.close()
    if "SUPPLIER_WIT_PASS" in out:
        print("GO_LIVE_SUPPLIER_WIT_OK", flush=True)
        return 0
    print("GO_LIVE_SUPPLIER_WIT_FAIL", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
