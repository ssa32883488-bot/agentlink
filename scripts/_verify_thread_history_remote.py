# -*- coding: utf-8 -*-
"""远端验收：threads 创建 + chat 落盘 + conversations 回读。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")


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
    print("$", cmd, flush=True)
    _i, o, e = c.exec_command(cmd, timeout=120, get_pty=True)
    out = o.read().decode("utf-8", errors="replace")
    err = e.read().decode("utf-8", errors="replace")
    text = (out or "") + (("\n" + err) if err else "")
    print(text[-2500:], flush=True)
    return text


def verify_buyer() -> None:
    print("==== verify buyer ====", flush=True)
    c = connect("buyer")
    run(c, "ss -lntp | grep -E '8010|8011|8020' || true")
    run(c, "journalctl -u agentlink-buyer-a -n 30 --no-pager | tail -n 30")
    # try http then https
    for scheme in ("http", "https"):
        base = f"{scheme}://127.0.0.1:8010"
        flag = "-sk" if scheme == "https" else "-s"
        run(
            c,
            f"curl {flag} -o /tmp/th.json -w '%{{http_code}}' '{base}/api/erp/chat/threads'; echo; "
            f"head -c 400 /tmp/th.json; echo",
        )
    # full flow over http (most likely)
    run(
        c,
        r"""python3 - <<'PY'
import json, urllib.request
base='http://127.0.0.1:8010'
def req(method, path, body=None):
    data=None if body is None else json.dumps(body).encode()
    r=urllib.request.Request(base+path, data=data, method=method)
    if body is not None: r.add_header('Content-Type','application/json')
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())
code, th = req('POST','/api/erp/chat/threads',{'title':'远端验收窗'})
print('CREATE', code, th.get('id'), th.get('title'))
tid=th['id']
code, chat = req('POST','/api/erp/chat',{'text':'采购80套脚轮做历史验证','thread_id':tid})
print('CHAT', code, chat.get('ok'), chat.get('thread_id'), (chat.get('reply') or '')[:40])
code, conv = req('GET', f'/api/erp/conversations?thread_id={tid}')
items=conv.get('items') or []
print('CONV', code, len(items), conv.get('thread_id'))
assert len(items)>=2, items
code, threads = req('GET','/api/erp/chat/threads')
assert any(x.get('id')==tid for x in (threads.get('items') or []))
print('BUYER_OK')
PY""",
    )
    c.close()


def verify_supplier() -> None:
    print("==== verify supplier ====", flush=True)
    c = connect("supplier")
    run(c, "journalctl -u agentlink-supplier-a -n 20 --no-pager | tail -n 20")
    run(
        c,
        r"""python3 - <<'PY'
import json, urllib.request
base='http://127.0.0.1:8011'
def req(method, path, body=None):
    data=None if body is None else json.dumps(body).encode()
    r=urllib.request.Request(base+path, data=data, method=method)
    if body is not None: r.add_header('Content-Type','application/json')
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())
code, th = req('POST','/api/erp/chat/threads',{'title':'供应历史窗'})
print('CREATE', code, th.get('id'), th.get('title'))
tid=th['id']
code, chat = req('POST','/api/erp/chat',{'text':'你好，报一下库存','thread_id':tid})
print('CHAT', code, chat.get('ok'), chat.get('thread_id'), (chat.get('reply') or chat.get('message') or '')[:40])
code, conv = req('GET', f'/api/erp/conversations?thread_id={tid}')
items=conv.get('items') or []
print('CONV', code, len(items), conv.get('thread_id'))
assert len(items)>=2, items
print('SUPPLIER_OK')
PY""",
    )
    c.close()


if __name__ == "__main__":
    verify_buyer()
    verify_supplier()
    print("VERIFY_DONE", flush=True)
