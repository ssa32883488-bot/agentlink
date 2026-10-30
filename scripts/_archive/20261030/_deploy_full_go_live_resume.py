# -*- coding: utf-8 -*-
"""Resume go-live after interrupt: patch env, restart, then Aliyun sync+restart."""
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

ALIYUN_RELS = [
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
    "commerce/env_loader.py",
    "docs/aic码.md",
]

# tencent critical set (already uploaded once; re-put key files cheaply)
TENCENT_RELS = [
    "commerce/chat_buyer_wit.py",
    "commerce/choice_actions.py",
    "commerce/auction_suitability.py",
    "commerce/buyer_tools/service.py",
    "commerce/buyer_tools/schemas.py",
    "commerce/buyer_tools/memory_store.py",
    "commerce/buyer_tools/__init__.py",
    "commerce/discovery.py",
    "commerce/flow_service.py",
    "commerce/flow_routes.py",
    "commerce/group_mq.py",
    "commerce/group_routes.py",
    "commerce/order_tickets.py",
    "acs/buyer-agent-a.acs.json",
    "acs/buyer-agent-b.acs.json",
    "acs/logistics-agent.acs.json",
    "acs/supplier-agent-a.acs.json",
    "acs/supplier-agent-b.acs.json",
    "acs/supplier-agent-c.acs.json",
    "docs/aic码.md",
    "docs/design_dual_path_group_auction.md",
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


def ensure_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
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


def put_rels(c: paramiko.SSHClient, rels: list[str]) -> int:
    sftp = c.open_sftp()
    n = 0
    for rel in rels:
        local = ROOT / rel
        if not local.is_file():
            # try glob for supplier_common / runtime
            continue
        remote = f"/opt/agentlink/{rel}"
        ensure_dir(sftp, posixpath.dirname(remote))
        sftp.put(str(local), remote)
        n += 1
    # agentlink_runtime + supplier_common trees
    for pattern in ("agentlink_runtime/**/*.py", "agents/supplier_common/**/*.py"):
        for local in ROOT.glob(pattern):
            if not local.is_file() or "__pycache__" in local.parts:
                continue
            rel = local.relative_to(ROOT).as_posix()
            remote = f"/opt/agentlink/{rel}"
            ensure_dir(sftp, posixpath.dirname(remote))
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
                print("updated", path, flush=True)
    except Exception as exc:  # noqa: BLE001
        print("etc:", exc, flush=True)
    sftp.close()


def main() -> None:
    print("==== TENCENT resume ====", flush=True)
    c = connect("81.70.46.119", key=True)
    n = put_rels(c, TENCENT_RELS)
    print("uploaded", n, flush=True)
    patch_env(c)
    print(
        run(
            c,
            r"""
set +e
grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_).*AIC=' /opt/agentlink/.env
systemctl daemon-reload
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics
systemctl restart agentlink-ui-buyer-a agentlink-ui-buyer-b 2>/dev/null || true
sleep 14
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics
for p in 8010 8012 8015; do echo -n "H:$p "; curl -sk --connect-timeout 5 https://127.0.0.1:$p/health; echo; done
cd /opt/agentlink && .venv/bin/python - <<'PY'
from commerce.auction_suitability import assess_group_auction_suitability
from commerce.choice_actions import post_quote_choices
from commerce import chat_buyer_wit
caps = chat_buyer_wit._build_capabilities(None)
names = [getattr(x, '__name__', '') for x in caps]
assert 'flow_decide_auction' in names or any('auction' in n for n in names)
print('TENCENT_OK caps', len(caps), 'auction_tools', [n for n in names if 'auction' in n])
PY
""",
            timeout=180,
        ),
        flush=True,
    )
    c.close()

    print("==== ALIYUN deploy ====", flush=True)
    c2 = connect("39.105.20.113", key=False)
    # expand aliyun list with acs + runtime
    rels = list(ALIYUN_RELS)
    for acs in (
        "acs/buyer-agent-a.acs.json",
        "acs/buyer-agent-b.acs.json",
        "acs/logistics-agent.acs.json",
        "acs/supplier-agent-a.acs.json",
        "acs/supplier-agent-b.acs.json",
        "acs/supplier-agent-c.acs.json",
    ):
        rels.append(acs)
    n2 = put_rels(c2, rels)
    print("uploaded", n2, flush=True)
    patch_env(c2)
    print(
        run(
            c2,
            r"""
set +e
grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_).*AIC=' /opt/agentlink/.env
systemctl restart agentlink-erp-a agentlink-erp-b agentlink-erp-c 2>/dev/null || true
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for i in $(seq 1 18); do
  a=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8011/health || true)
  b=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8013/health || true)
  c=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:8014/health || true)
  echo "try$i a=$a b=$b c=$c"
  [ "$a$b$c" = 200200200 ] && break
  sleep 5
done
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c
for p in 8011 8013 8014; do echo -n "H:$p "; curl -sk --connect-timeout 5 https://127.0.0.1:$p/health; echo; done
echo ALIYUN_OK
""",
            timeout=240,
        ),
        flush=True,
    )
    c2.close()
    print("ALL_DEPLOY_DONE", flush=True)


if __name__ == "__main__":
    main()
