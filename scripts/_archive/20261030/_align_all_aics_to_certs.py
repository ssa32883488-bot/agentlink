# -*- coding: utf-8 -*-
"""Align agent AIC env vars to live mTLS cert CNs on Tencent (+ suppliers on Aliyun if reachable)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
BUYER = "81.70.46.119"
SUPPLIER = "39.105.20.113"
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

# map role -> cert path on that host
TENCENT_CERTS = {
    "BUYER_A_AIC": "/opt/agentlink/certs/platform/buyer-a/agent-cert.pem",
    "BUYER_B_AIC": "/opt/agentlink/certs/platform/buyer-b/agent-cert.pem",
    "LOGISTICS_AIC": "/opt/agentlink/certs/platform/logistics/agent-cert.pem",
}
ALIYUN_CERTS = {
    "SUPPLIER_A_AIC": "/opt/agentlink/certs/platform/supplier-a/agent-cert.pem",
    "SUPPLIER_B_AIC": "/opt/agentlink/certs/platform/supplier-b/agent-cert.pem",
    "SUPPLIER_C_AIC": "/opt/agentlink/certs/platform/supplier-c/agent-cert.pem",
}


def cn_of(c: paramiko.SSHClient, cert: str) -> str:
    _, o, e = c.exec_command(
        f"openssl x509 -in {cert} -noout -subject 2>/dev/null | sed -n 's/.*CN *= *\\([^,]*\\).*/\\1/p' | tr -d ' '",
        timeout=30,
    )
    return (o.read() + e.read()).decode().strip()


def patch_envs(c: paramiko.SSHClient, mapping: dict[str, str]) -> None:
    # build a python remote patcher to avoid shell escaping hell
    payload = json.dumps(mapping, ensure_ascii=False)
    remote = f"""
python3 - <<'PY'
import glob, json, re
mapping = json.loads('''{payload}''')
files = ['/opt/agentlink/.env'] + glob.glob('/etc/agentlink/*.env')
for f in files:
    try:
        text = open(f, encoding='utf-8').read()
    except Exception as e:
        print('skip', f, e)
        continue
    orig = text
    for k, v in mapping.items():
        if re.search(rf'^{k}=.*$', text, flags=re.M):
            text = re.sub(rf'^{k}=.*$', f'{{k}}={{v}}', text, flags=re.M)
        else:
            text = text.rstrip() + f'\\n{{k}}={{v}}\\n'
    if text != orig:
        open(f, 'w', encoding='utf-8').write(text)
        print('patched', f)
    else:
        print('unchanged', f)
# patch ACS jsons if present
import os
acs_map = {{
    'BUYER_A_AIC': 'buyer-a',
    'BUYER_B_AIC': 'buyer-b',
    'LOGISTICS_AIC': 'logistics',
    'SUPPLIER_A_AIC': 'supplier-a',
    'SUPPLIER_B_AIC': 'supplier-b',
    'SUPPLIER_C_AIC': 'supplier-c',
}}
for envk, short in acs_map.items():
    if envk not in mapping:
        continue
    for cand in [
        f'/opt/agentlink/acs/{{short}}-agent.acs.json',
        f'/opt/agentlink/acs/{{short}}.acs.json',
        f'/opt/agentlink/acs/{{short}}-agent-a.acs.json' if short=='buyer-a' else '',
    ]:
        if not cand or not os.path.exists(cand):
            continue
        d=json.load(open(cand, encoding='utf-8'))
        d['aic']=mapping[envk]
        json.dump(d, open(cand,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
        print('acs', cand, mapping[envk])
print('DONE_PATCH')
PY
"""
    # fix the f-string braces for remote python - I used doubled braces wrong.
    # Rewrite more carefully.
    raise NotImplementedError


def patch_envs_v2(c: paramiko.SSHClient, mapping: dict[str, str]) -> str:
    sftp = c.open_sftp()
    remote_py = "/tmp/align_aics.py"
    body = (
        "import glob, json, re, os\n"
        f"mapping = {json.dumps(mapping, ensure_ascii=False)}\n"
        "files = ['/opt/agentlink/.env'] + glob.glob('/etc/agentlink/*.env')\n"
        "for f in files:\n"
        "    try:\n"
        "        text = open(f, encoding='utf-8').read()\n"
        "    except Exception as e:\n"
        "        print('skip', f, e); continue\n"
        "    orig = text\n"
        "    for k, v in mapping.items():\n"
        "        if re.search(rf'^{k}=.*$', text, flags=re.M):\n"
        "            text = re.sub(rf'^{k}=.*$', f'{k}={v}', text, flags=re.M)\n"
        "        else:\n"
        "            text = text.rstrip() + f'\\n{k}={v}\\n'\n"
        "    if text != orig:\n"
        "        open(f, 'w', encoding='utf-8').write(text)\n"
        "        print('patched', f)\n"
        "    else:\n"
        "        print('unchanged', f)\n"
        "acs_map = {\n"
        "  'BUYER_A_AIC': ['buyer-agent-a.acs.json','buyer-a.acs.json','buyer-a-agent.acs.json'],\n"
        "  'BUYER_B_AIC': ['buyer-agent-b.acs.json','buyer-b.acs.json','buyer-b-agent.acs.json'],\n"
        "  'LOGISTICS_AIC': ['logistics-agent.acs.json','logistics.acs.json'],\n"
        "  'SUPPLIER_A_AIC': ['supplier-agent-a.acs.json','supplier-a.acs.json'],\n"
        "  'SUPPLIER_B_AIC': ['supplier-agent-b.acs.json','supplier-b.acs.json'],\n"
        "  'SUPPLIER_C_AIC': ['supplier-agent-c.acs.json','supplier-c.acs.json'],\n"
        "}\n"
        "for envk, names in acs_map.items():\n"
        "    if envk not in mapping: continue\n"
        "    for name in names:\n"
        "        path = f'/opt/agentlink/acs/{name}'\n"
        "        if not os.path.exists(path): continue\n"
        "        d=json.load(open(path, encoding='utf-8'))\n"
        "        d['aic']=mapping[envk]\n"
        "        json.dump(d, open(path,'w',encoding='utf-8'), ensure_ascii=False, indent=2)\n"
        "        print('acs', path, mapping[envk])\n"
        "print('DONE_PATCH')\n"
    )
    # The f'{k}={v}' inside the string will be evaluated locally - BAD.
    # Write raw file with format carefully.
    body = r'''import glob, json, re, os
mapping = %s
files = ["/opt/agentlink/.env"] + glob.glob("/etc/agentlink/*.env")
for f in files:
    try:
        text = open(f, encoding="utf-8").read()
    except Exception as e:
        print("skip", f, e)
        continue
    orig = text
    for k, v in mapping.items():
        pat = r"^" + re.escape(k) + r"=.*$"
        if re.search(pat, text, flags=re.M):
            text = re.sub(pat, k + "=" + v, text, flags=re.M)
        else:
            text = text.rstrip() + "\n" + k + "=" + v + "\n"
    if text != orig:
        open(f, "w", encoding="utf-8").write(text)
        print("patched", f)
    else:
        print("unchanged", f)
acs_map = {
  "BUYER_A_AIC": ["buyer-agent-a.acs.json","buyer-a.acs.json","buyer-a-agent.acs.json"],
  "BUYER_B_AIC": ["buyer-agent-b.acs.json","buyer-b.acs.json","buyer-b-agent.acs.json"],
  "LOGISTICS_AIC": ["logistics-agent.acs.json","logistics.acs.json"],
  "SUPPLIER_A_AIC": ["supplier-agent-a.acs.json","supplier-a.acs.json"],
  "SUPPLIER_B_AIC": ["supplier-agent-b.acs.json","supplier-b.acs.json"],
  "SUPPLIER_C_AIC": ["supplier-agent-c.acs.json","supplier-c.acs.json"],
}
for envk, names in acs_map.items():
    if envk not in mapping:
        continue
    for name in names:
        path = "/opt/agentlink/acs/" + name
        if not os.path.exists(path):
            continue
        d = json.load(open(path, encoding="utf-8"))
        d["aic"] = mapping[envk]
        json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("acs", path, mapping[envk])
print("DONE_PATCH")
''' % (json.dumps(mapping, ensure_ascii=False),)
    with sftp.file(remote_py, "w") as fh:
        fh.write(body)
    sftp.close()
    _, o, e = c.exec_command(f"python3 {remote_py}", timeout=60)
    return (o.read() + e.read()).decode("utf-8", "replace")


def main() -> None:
    b = paramiko.SSHClient()
    b.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    b.connect(BUYER, username="root", pkey=paramiko.RSAKey.from_private_key_file(str(PEM)), timeout=40, allow_agent=False, look_for_keys=False)

    mapping: dict[str, str] = {}
    for k, path in TENCENT_CERTS.items():
        cn = cn_of(b, path)
        print(f"tencent {k} <= {cn}", flush=True)
        if cn:
            mapping[k] = cn

    # Also read supplier CNs from aliyun and put into tencent env (buyers need supplier AICs)
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    s.connect(SUPPLIER, username="root", password=PW, timeout=40, allow_agent=False, look_for_keys=False)
    for k, path in ALIYUN_CERTS.items():
        cn = cn_of(s, path)
        print(f"aliyun {k} <= {cn}", flush=True)
        if cn:
            mapping[k] = cn

    print("--- patch tencent ---", flush=True)
    print(patch_envs_v2(b, mapping), flush=True)
    _, o, e = b.exec_command(
        "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; sleep 3; "
        "systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics; "
        "grep -E 'BUYER_A_AIC|BUYER_B_AIC|LOGISTICS_AIC|SUPPLIER_._AIC' /etc/agentlink/buyer-a.env /etc/agentlink/logistics.env | head -40",
        timeout=90,
    )
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    b.close()

    print("--- patch aliyun ---", flush=True)
    print(patch_envs_v2(s, mapping), flush=True)
    _, o, e = s.exec_command(
        "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 3; "
        "systemctl is-active agentlink-supplier-a; "
        "grep -E 'BUYER_A_AIC|LOGISTICS_AIC|SUPPLIER_._AIC' /opt/agentlink/.env /etc/agentlink/*.env 2>/dev/null | head -40",
        timeout=90,
    )
    print((o.read() + e.read()).decode("utf-8", "replace"), flush=True)
    s.close()
    print("ALIGN_ALL_AICS_DONE", flush=True)


if __name__ == "__main__":
    main()
