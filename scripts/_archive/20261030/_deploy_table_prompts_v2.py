# -*- coding: utf-8 -*-
"""Deploy table presentation hints + prompts; optional Java jars if present."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

PY_FILES = [
    "commerce/chat_buyer_wit.py",
    "commerce/chat_supplier_wit.py",
    "commerce/buyer_tools/service.py",
]
JAR_MAP = {
    "java-suppliers/supplier-a/build/libs/supplier-a-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-a.jar",
    "java-suppliers/supplier-b/build/libs/supplier-b-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-b.jar",
    "java-suppliers/supplier-c/build/libs/supplier-c-0.1.0.jar": "/opt/agentlink/java-suppliers/supplier-c.jar",
}


def put_files(c: paramiko.SSHClient, rels: list[str]) -> None:
    sftp = c.open_sftp()
    for rel in rels:
        sftp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
        print("put", rel, flush=True)
    sftp.close()


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 240) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def main() -> None:
    print("==== TENCENT ====", flush=True)
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=40,
        allow_agent=False,
        look_for_keys=False,
    )
    put_files(b, PY_FILES)
    print(
        run(
            b,
            "grep -n presentation_hint /opt/agentlink/commerce/buyer_tools/service.py | head; "
            "systemctl restart agentlink-buyer-a agentlink-buyer-b; sleep 5; "
            "systemctl is-active agentlink-buyer-a agentlink-buyer-b; "
            "curl -sk https://127.0.0.1:8010/health; echo",
        ),
        flush=True,
    )
    # quick table smoke via chat API if available
    print(
        run(
            b,
            r"""
cd /opt/agentlink && .venv/bin/python - <<'PY'
import asyncio, re, os
from pathlib import Path
for f in ('/opt/agentlink/.env','/etc/agentlink/buyer-a.env'):
    p=Path(f)
    if not p.is_file(): continue
    for raw in p.read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ['BUYER_AGENT_ID']='buyer-a'
from commerce.chat_buyer_wit import handle_buyer_chat_wit, configure
configure(agent_id='buyer-a')
async def main():
    out = await handle_buyer_chat_wit('请用表格列出当前库存告警（若无告警也用表说明）', run_rfq=None, thread_id='table-smoke-1')
    text = ''
    if isinstance(out, dict):
        text = str(out.get('reply') or out.get('text') or out.get('message') or out)
    else:
        text = str(out)
    print('REPLY_HEAD', text[:800].replace('\n','\\n'))
    ok = bool(re.search(r'\|.+\|.+\n\|?\s*[-:]+', text))
    print('HAS_MD_TABLE', ok)
asyncio.run(main())
PY
""",
            timeout=180,
        ),
        flush=True,
    )
    b.close()

    print("==== ALIYUN ====", flush=True)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect("39.105.20.113", username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    put_files(s, ["commerce/chat_supplier_wit.py", "commerce/chat_buyer_wit.py"])
    jars = []
    for local, remote in JAR_MAP.items():
        p = ROOT / local
        if p.is_file():
            jars.append((local, remote))
    if jars:
        sftp = s.open_sftp()
        for local, remote in jars:
            # try both known remote paths
            for rem in (remote, remote.replace("/java-suppliers/", "/java/")):
                try:
                    sftp.put(str(ROOT / local), rem)
                    print("put jar", local, "->", rem, flush=True)
                except Exception as exc:  # noqa: BLE001
                    print("jar skip", rem, exc, flush=True)
        sftp.close()
        print(
            run(
                s,
                "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; "
                "systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp; "
                "sleep 8; systemctl is-active agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp",
            ),
            flush=True,
        )
    else:
        print(
            run(
                s,
                "systemctl restart agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp; "
                "sleep 3; systemctl is-active agentlink-supplier-a-erp agentlink-supplier-b-erp agentlink-supplier-c-erp; "
                "echo NO_JARS_PY_ONLY",
            ),
            flush=True,
        )
    s.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
