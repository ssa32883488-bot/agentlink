# -*- coding: utf-8 -*-
"""Full go-live: sync code + AICs to Tencent (buyers/logistics) and Aliyun (suppliers), restart, health."""
from __future__ import annotations

import os
import posixpath
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

AICS = {
    "BUYER_A_AIC": "1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW",
    "BUYER_B_AIC": "1.2.156.3088.1.BUPT.2HY2P9.21P09A.N3GL7K.11NO",
    "LOGISTICS_AIC": "1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS",
    "SUPPLIER_A_AIC": "1.2.156.3088.1.BUPT.2HY2P9.NH4J42.CV501K.0U11",
    "SUPPLIER_B_AIC": "1.2.156.3088.1.BUPT.2HY2P9.SHDUXP.AKGA0G.0768",
    "SUPPLIER_C_AIC": "1.2.156.3088.1.BUPT.2HY2P9.8R39K3.RQIABQ.1ABF",
}

# Shared / buyer-side trees (Tencent)
TENCENT_GLOBS = [
    "commerce/**/*.py",
    "agentlink_runtime/**/*.py",
    "agents/buyer_a/**/*",
    "agents/buyer_b/**/*",
    "agents/logistics/**/*",
    "agents/supplier_common/**/*.py",
    "acs/*.acs.json",
    "scripts/run_agent_https.py",
    "ui/**/*.py",
    "ui/static/**/*",
    "docs/aic码.md",
    "docs/design_dual_path_group_auction.md",
]

# Aliyun: keep java jars as-is; sync python sidecars / discovery / acs / shared
ALIYUN_GLOBS = [
    "commerce/discovery.py",
    "commerce/merchant.py",
    "commerce/merchant_profiles.yaml",
    "commerce/seat_catalog.py",
    "commerce/seed.py",
    "commerce/db.py",
    "commerce/notify.py",
    "commerce/tickets.py",
    "commerce/mailbox.py",
    "commerce/office_routes.py",
    "commerce/order_tickets.py",
    "commerce/logistics_tickets.py",
    "commerce/group_mq.py",
    "commerce/group_routes.py",
    "commerce/amp_log.py",
    "commerce/chat_supplier_wit.py",
    "commerce/supplier_routes.py",
    "commerce/rfq_bridge.py",
    "agents/supplier_common/**/*.py",
    "agentlink_runtime/**/*.py",
    "acs/*.acs.json",
    "docs/aic码.md",
]


def connect(host: str, *, key: bool) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = {
        "hostname": host,
        "username": "root",
        "timeout": 50,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if key:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 240) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    o.channel.settimeout(timeout)
    return (o.read() + e.read()).decode("utf-8", errors="replace")


def upsert_env_text(text: str) -> str:
    lines = text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in AICS:
                out.append(f"{k}={AICS[k]}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in AICS.items():
        if k not in seen:
            out.append(f"{k}={v}")
    return "\n".join(out).rstrip() + "\n"


def collect(globs: list[str]) -> list[Path]:
    files: list[Path] = []
    for g in globs:
        if "**" in g or "*" in g:
            files.extend(p for p in ROOT.glob(g) if p.is_file())
        else:
            p = ROOT / g
            if p.is_file():
                files.append(p)
    # unique
    seen: set[Path] = set()
    out: list[Path] = []
    for p in files:
        rp = p.resolve()
        if rp in seen:
            continue
        # skip caches / venv junk
        if any(x in rp.parts for x in (".venv", "__pycache__", "node_modules", ".git")):
            continue
        seen.add(rp)
        out.append(p)
    return out


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = remote_dir.strip("/").split("/")
    cur = ""
    for part in parts:
        cur = f"{cur}/{part}"
        try:
            sftp.stat(cur)
        except OSError:
            try:
                sftp.mkdir(cur)
            except OSError:
                pass


def upload_files(c: paramiko.SSHClient, files: list[Path]) -> int:
    sftp = c.open_sftp()
    n = 0
    for local in files:
        rel = local.relative_to(ROOT).as_posix()
        remote = f"/opt/agentlink/{rel}"
        ensure_remote_dir(sftp, posixpath.dirname(remote))
        sftp.put(str(local), remote)
        n += 1
    sftp.close()
    return n


def patch_env(c: paramiko.SSHClient) -> None:
    sftp = c.open_sftp()
    with sftp.file("/opt/agentlink/.env", "r") as f:
        data = f.read()
        text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
    with sftp.file("/opt/agentlink/.env", "w") as f:
        f.write(upsert_env_text(text))
    try:
        for name in sftp.listdir("/etc/agentlink"):
            if not name.endswith(".env"):
                continue
            path = f"/etc/agentlink/{name}"
            with sftp.file(path, "r") as f:
                data = f.read()
                t = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
            nt = upsert_env_text(t)
            if nt != t:
                with sftp.file(path, "w") as f:
                    f.write(nt)
    except Exception as exc:  # noqa: BLE001
        print("etc env note:", exc, flush=True)
    sftp.close()


def deploy_tencent() -> None:
    print("\n==== TENCENT full deploy ====", flush=True)
    files = collect(TENCENT_GLOBS)
    print(f"files to sync: {len(files)}", flush=True)
    c = connect("81.70.46.119", key=True)
    n = upload_files(c, files)
    print(f"uploaded {n}", flush=True)
    patch_env(c)
    out = run(
        c,
        r"""
set +e
grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_).*AIC=' /opt/agentlink/.env
systemctl daemon-reload
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
# UI units if present
systemctl restart agentlink-ui-buyer-a agentlink-ui-buyer-b 2>/dev/null || true
systemctl restart agentlink-ui-8090 agentlink-ui-8092 2>/dev/null || true
sleep 12
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
for p in 8010 8012 8015; do
  echo -n "H:$p "
  curl -sk --connect-timeout 5 https://127.0.0.1:$p/health; echo
done
# compile check dual-path modules
cd /opt/agentlink && .venv/bin/python - <<'PY'
from commerce.auction_suitability import assess_group_auction_suitability
from commerce import choice_actions, chat_buyer_wit
print('import_ok', hasattr(chat_buyer_wit, '_build_capabilities'))
caps = chat_buyer_wit._build_capabilities(None)
ids = []
for c in caps:
    # capability wrappers may expose __name__ or capability id via attrs
    ids.append(getattr(c, '__name__', str(c))[:40])
print('cap_count', len(caps))
print('TENCENT_MODULE_OK')
PY
""",
        timeout=180,
    )
    print(out, flush=True)
    c.close()


def deploy_aliyun() -> None:
    print("\n==== ALIYUN full deploy ====", flush=True)
    files = collect(ALIYUN_GLOBS)
    # also sync java resource policies if present
    for extra in ROOT.glob("java-suppliers/*/src/main/resources/policy.yaml"):
        files.append(extra)
    print(f"files to sync: {len(files)}", flush=True)
    c = connect("39.105.20.113", key=False)
    n = upload_files(c, files)
    print(f"uploaded {n}", flush=True)
    patch_env(c)
    out = run(
        c,
        r"""
set +e
grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_).*AIC=' /opt/agentlink/.env
# ERP sidecars if exist
systemctl restart agentlink-erp-a agentlink-erp-b agentlink-erp-c 2>/dev/null || true
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for i in $(seq 1 16); do
  a=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8011/health || true)
  b=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8013/health || true)
  c=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8014/health || true)
  echo "try$i a=$a b=$b c=$c"
  [ "$a$b$c" = 200200200 ] && break
  sleep 5
done
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for p in 8011 8013 8014; do
  echo -n "H:$p "
  curl -sk --connect-timeout 5 https://127.0.0.1:$p/health; echo
done
echo ALIYUN_DONE
""",
        timeout=240,
    )
    print(out, flush=True)
    c.close()


def main() -> None:
    deploy_tencent()
    deploy_aliyun()
    print("\nALL_DEPLOY_DONE", flush=True)


if __name__ == "__main__":
    main()
