# -*- coding: utf-8 -*-
"""Ensure remote .env AICs + restart + health; mkdir buyer_tools on Aliyun if needed."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
ROOT = Path(__file__).resolve().parents[1]

ENV_SNIP = """
BUYER_A_AIC=1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW
BUYER_B_AIC=1.2.156.3088.1.BUPT.2HY2P9.21P09A.N3GL7K.11NO
LOGISTICS_AIC=1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS
SUPPLIER_A_AIC=1.2.156.3088.1.BUPT.2HY2P9.NH4J42.CV501K.0U11
SUPPLIER_B_AIC=1.2.156.3088.1.BUPT.2HY2P9.SHDUXP.AKGA0G.0768
SUPPLIER_C_AIC=1.2.156.3088.1.BUPT.2HY2P9.8R39K3.RQIABQ.1ABF
"""


def upsert_env(text: str) -> str:
    lines = text.splitlines()
    kv = {}
    for line in ENV_SNIP.strip().splitlines():
        k, v = line.split("=", 1)
        kv[k] = v
    out = []
    seen = set()
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in kv:
                out.append(f"{k}={kv[k]}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in kv.items():
        if k not in seen:
            out.append(f"{k}={v}")
    return "\n".join(out) + "\n"


def fix_host(host: str, *, key: bool, suppliers: bool) -> None:
    print(f"==== {host} ====", flush=True)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if key:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    sftp = c.open_sftp()
    # upsert /opt/agentlink/.env
    with sftp.file("/opt/agentlink/.env", "r") as f:
        data = f.read()
        text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
    new = upsert_env(text)
    with sftp.file("/opt/agentlink/.env", "w") as f:
        f.write(new)
    # also /etc/agentlink/*.env
    try:
        for name in sftp.listdir("/etc/agentlink"):
            if not name.endswith(".env"):
                continue
            path = f"/etc/agentlink/{name}"
            with sftp.file(path, "r") as f:
                data = f.read()
                t = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
            nt = upsert_env(t)
            if nt != t:
                with sftp.file(path, "w") as f:
                    f.write(nt)
                print("updated", path, flush=True)
    except Exception as exc:
        print("etc env skip", exc, flush=True)

    if suppliers:
        # ensure dirs and put discovery only
        for d in ("/opt/agentlink/commerce", "/opt/agentlink/acs"):
            try:
                sftp.stat(d)
            except OSError:
                # mkdir -p via shell
                pass
    # put discovery
    sftp.put(str(ROOT / "commerce/discovery.py"), "/opt/agentlink/commerce/discovery.py")
    for acs in (
        "buyer-agent-a.acs.json",
        "buyer-agent-b.acs.json",
        "logistics-agent.acs.json",
        "supplier-agent-a.acs.json",
        "supplier-agent-b.acs.json",
        "supplier-agent-c.acs.json",
    ):
        sftp.put(str(ROOT / "acs" / acs), f"/opt/agentlink/acs/{acs}")
    if not suppliers:
        # tencent buyers need buyer_tools
        try:
            sftp.mkdir("/opt/agentlink/commerce/buyer_tools")
        except OSError:
            pass
        for rel in (
            "commerce/buyer_tools/service.py",
            "commerce/buyer_tools/__init__.py",
            "commerce/buyer_tools/schemas.py",
            "commerce/buyer_tools/memory_store.py",
            "commerce/auction_suitability.py",
            "commerce/choice_actions.py",
            "commerce/chat_buyer_wit.py",
        ):
            lp = ROOT / rel
            if lp.is_file():
                sftp.put(str(lp), f"/opt/agentlink/{rel}")
                print("put", rel, flush=True)
    sftp.close()

    cmd = r"""
set -e
grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_).*AIC=' /opt/agentlink/.env
systemctl daemon-reload
if systemctl list-unit-files | grep -q agentlink-buyer-a; then
  systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
fi
if systemctl list-unit-files | grep -q agentlink-supplier-a; then
  systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
fi
sleep 12
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics 2>/dev/null || true
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c 2>/dev/null || true
for p in 8010 8011 8012 8013 8014 8015; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 https://127.0.0.1:$p/health || true)
  echo "health:$p=$code"
done
# print aic from health if any
for p in 8010 8015 8011 8013 8014; do
  echo -n "body:$p "
  curl -sk --connect-timeout 3 https://127.0.0.1:$p/health 2>/dev/null | head -c 200; echo
done
journalctl -u agentlink-buyer-a -n 15 --no-pager 2>/dev/null | tail -n 15 || true
"""
    _, o, e = c.exec_command(cmd, timeout=180, get_pty=True)
    print((o.read() + e.read()).decode("utf-8", errors="replace"))
    c.close()


def main() -> None:
    fix_host("81.70.46.119", key=True, suppliers=False)
    fix_host("39.105.20.113", key=False, suppliers=True)


if __name__ == "__main__":
    main()
