# -*- coding: utf-8 -*-
"""Apply new AICs to Tencent + Aliyun .env / ACS, restart, verify /health aic."""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")
ROOT = Path(__file__).resolve().parents[1]

AICS = {
    "BUYER_A_AIC": "1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW",
    "BUYER_B_AIC": "1.2.156.3088.1.BUPT.2HY2P9.21P09A.N3GL7K.11NO",
    "LOGISTICS_AIC": "1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS",
    "SUPPLIER_A_AIC": "1.2.156.3088.1.BUPT.2HY2P9.NH4J42.CV501K.0U11",
    "SUPPLIER_B_AIC": "1.2.156.3088.1.BUPT.2HY2P9.SHDUXP.AKGA0G.0768",
    "SUPPLIER_C_AIC": "1.2.156.3088.1.BUPT.2HY2P9.8R39K3.RQIABQ.1ABF",
}

ACS_FILES = [
    "buyer-agent-a.acs.json",
    "buyer-agent-b.acs.json",
    "logistics-agent.acs.json",
    "supplier-agent-a.acs.json",
    "supplier-agent-b.acs.json",
    "supplier-agent-c.acs.json",
]


def upsert_env(text: str) -> str:
    lines = text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        raw = line
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in AICS:
                out.append(f"{k}={AICS[k]}")
                seen.add(k)
                continue
        out.append(raw)
    for k, v in AICS.items():
        if k not in seen:
            out.append(f"{k}={v}")
    return "\n".join(out).rstrip() + "\n"


def connect(host: str, *, use_key: bool) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = {
        "hostname": host,
        "username": "root",
        "timeout": 45,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if use_key:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def apply(host: str, *, use_key: bool, role: str) -> None:
    print(f"\n======== {host} ({role}) ========", flush=True)
    c = connect(host, use_key=use_key)
    sftp = c.open_sftp()

    # .env
    with sftp.file("/opt/agentlink/.env", "r") as f:
        data = f.read()
        text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
    with sftp.file("/opt/agentlink/.env", "w") as f:
        f.write(upsert_env(text))
    print("wrote /opt/agentlink/.env AIC keys", flush=True)

    # /etc/agentlink/*.env
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
    except Exception as exc:  # noqa: BLE001
        print("etc env:", exc, flush=True)

    # ACS
    for acs in ACS_FILES:
        local = ROOT / "acs" / acs
        if local.is_file():
            sftp.put(str(local), f"/opt/agentlink/acs/{acs}")
    # discovery fingerprint tokens
    disc = ROOT / "commerce" / "discovery.py"
    if disc.is_file():
        sftp.put(str(disc), "/opt/agentlink/commerce/discovery.py")
    # buyer tools only on tencent
    if role == "tencent":
        for rel in (
            "commerce/buyer_tools/service.py",
            "commerce/chat_buyer_wit.py",
            "commerce/choice_actions.py",
            "commerce/auction_suitability.py",
        ):
            lp = ROOT / rel
            if lp.is_file():
                try:
                    sftp.put(str(lp), f"/opt/agentlink/{rel}")
                    print("put", rel, flush=True)
                except Exception as exc:  # noqa: BLE001
                    print("put fail", rel, exc, flush=True)
    sftp.close()

    if role == "tencent":
        restart = r"""
set +e
grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_).*AIC=' /opt/agentlink/.env
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
sleep 15
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
for p in 8010 8012 8015; do
  echo -n "health:$p "
  curl -sk --connect-timeout 5 https://127.0.0.1:$p/health; echo
done
"""
    else:
        restart = r"""
set +e
grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_).*AIC=' /opt/agentlink/.env
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
# Java cold start ~60s
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  a=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8011/health || true)
  b=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8013/health || true)
  c=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8014/health || true)
  echo "try$i a=$a b=$b c=$c"
  [ "$a$b$c" = 200200200 ] && break
  sleep 5
done
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for p in 8011 8013 8014; do
  echo -n "health:$p "
  curl -sk --connect-timeout 5 https://127.0.0.1:$p/health; echo
done
"""
    print(run(c, restart, timeout=200), flush=True)
    c.close()


def main() -> None:
    apply("81.70.46.119", use_key=True, role="tencent")
    apply("39.105.20.113", use_key=False, role="aliyun")
    print("\nDONE", flush=True)


if __name__ == "__main__":
    main()
