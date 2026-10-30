# -*- coding: utf-8 -*-
"""把正式 AIC 写入腾讯云/阿里云 /opt/agentlink/.env 并重启服务。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko
import yaml
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
AIC_YAML = ROOT / "config" / "platform_aics.yaml"
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

BUYER = {"host": "81.70.46.119", "auth": "key", "role": "buyer"}
SUPPLIER = {
    "host": "39.105.20.113",
    "auth": "password",
    "password": os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"),
    "role": "supplier",
}

MERGE_PY = r'''
from pathlib import Path
env = Path("/opt/agentlink/.env")
snip = Path("/tmp/platform_aics.env").read_text(encoding="utf-8")
lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
kv = {}
order = []
for line in lines:
    if not line.strip() or line.strip().startswith("#") or "=" not in line:
        order.append(("raw", line))
        continue
    k, v = line.split("=", 1)
    kv[k] = v
    order.append(("kv", k))
for line in snip.splitlines():
    if not line.strip() or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    kv[k] = v
    if not any(t == "kv" and x == k for t, x in order):
        order.append(("kv", k))
out = []
seen = set()
for t, x in order:
    if t == "raw":
        out.append(x)
    elif x not in seen:
        out.append(f"{x}={kv[x]}")
        seen.add(x)
for k, v in kv.items():
    if k not in seen:
        out.append(f"{k}={v}")
env.write_text("\n".join(out) + "\n", encoding="utf-8")
print("merged", [k for k in kv if k.endswith("_AIC")])
'''


def connect(spec: dict) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if spec["auth"] == "key":
        key = paramiko.RSAKey.from_private_key_file(str(PEM))
        c.connect(spec["host"], username="root", pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            spec["host"],
            username="root",
            password=spec["password"],
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    print(f"$ {cmd[:160]}")
    _, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    print((out + err)[-2500:])
    if code != 0:
        raise SystemExit(f"remote exit {code}")
    return out


def push_pairs(c: paramiko.SSHClient, pairs: dict[str, str]) -> None:
    local = ROOT / "dist" / "_platform_aics_push.env"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("\n".join(f"{k}={v}" for k, v in pairs.items()) + "\n", encoding="utf-8")
    merge_local = ROOT / "dist" / "_merge_aics.py"
    merge_local.write_text(MERGE_PY, encoding="utf-8")
    with SCPClient(c.get_transport()) as scp:
        scp.put(str(local), "/tmp/platform_aics.env")
        scp.put(str(merge_local), "/tmp/merge_aics.py")
    run(c, "python3 /tmp/merge_aics.py")


def main() -> None:
    agents = yaml.safe_load(AIC_YAML.read_text(encoding="utf-8"))["agents"]
    buyer_pairs = {m["env"]: m["aic"] for m in agents.values() if m["host"] == "buyer"}
    supplier_pairs = {m["env"]: m["aic"] for m in agents.values() if m["host"] == "supplier"}
    buyer_pairs.update(supplier_pairs)

    targets = sys.argv[1:] or ["buyer", "supplier"]
    if "buyer" in targets:
        print("==== buyer ====")
        c = connect(BUYER)
        push_pairs(c, buyer_pairs)
        run(
            c,
            "systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics; sleep 3; "
            "curl -sk https://127.0.0.1:8010/health; echo; "
            "curl -sk https://127.0.0.1:8012/health; echo; "
            "curl -sk https://127.0.0.1:8015/health; echo",
        )
        c.close()
    if "supplier" in targets:
        print("==== supplier ====")
        c = connect(SUPPLIER)
        push_pairs(c, supplier_pairs)
        run(
            c,
            "systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c; sleep 3; "
            "curl -sk https://127.0.0.1:8011/health; echo; "
            "curl -sk https://127.0.0.1:8013/health; echo; "
            "curl -sk https://127.0.0.1:8014/health; echo",
        )
        c.close()
    print("AIC deploy done")


if __name__ == "__main__":
    main()
