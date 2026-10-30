# -*- coding: utf-8 -*-
"""Replace six AgentLink AICs across repo + push remotes."""
from __future__ import annotations

import os
import re
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

OLD_TO_NEW = {
    "1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW": "1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW",  # buyer-a
    "1.2.156.3088.1.BUPT.2HY2P9.21P09A.N3GL7K.11NO": "1.2.156.3088.1.BUPT.2HY2P9.21P09A.N3GL7K.11NO",  # buyer-b
    "1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS": "1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS",  # logistics
    "1.2.156.3088.1.BUPT.2HY2P9.NH4J42.CV501K.0U11": "1.2.156.3088.1.BUPT.2HY2P9.NH4J42.CV501K.0U11",  # supplier-a
    "1.2.156.3088.1.BUPT.2HY2P9.SHDUXP.AKGA0G.0768": "1.2.156.3088.1.BUPT.2HY2P9.SHDUXP.AKGA0G.0768",  # supplier-b
    "1.2.156.3088.1.BUPT.2HY2P9.8R39K3.RQIABQ.1ABF": "1.2.156.3088.1.BUPT.2HY2P9.8R39K3.RQIABQ.1ABF",  # supplier-c
}

# fingerprint segments used in discovery / resolve
TOKEN_MAP = {
    "ODIFWZ": "ODIFWZ",
    "FN5REA": "FN5REA",
    "21P09A": "21P09A",
    "N3GL7K": "N3GL7K",
    "ZBD999": "ZBD999",
    "NQXAR6": "NQXAR6",
    "NH4J42": "NH4J42",
    "CV501K": "CV501K",
    "SHDUXP": "SHDUXP",
    "AKGA0G": "AKGA0G",
    "8R39K3": "8R39K3",
    "RQIABQ": "RQIABQ",
}

SKIP_DIRS = {
    ".venv",
    "node_modules",
    "dist/_staging",
    "java-suppliers/supplier-a/build",
    "java-suppliers/supplier-b/build",
    "java-suppliers/supplier-c/build",
    "docs/report_draft",
    "data",
    "logs",
    "__pycache__",
}

EXT = {".py", ".json", ".md", ".env", ".yaml", ".yml", ".sh", ".txt", ".example"}


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    for d in SKIP_DIRS:
        if rel == d or rel.startswith(d + "/"):
            return True
    return False


def replace_text(text: str) -> str:
    for old, new in OLD_TO_NEW.items():
        text = text.replace(old, new)
    # token replace (longer first to avoid partial issues — all same length-ish)
    for old, new in sorted(TOKEN_MAP.items(), key=lambda x: -len(x[0])):
        text = text.replace(old, new)
    return text


def local_replace() -> list[str]:
    changed: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        if path.suffix.lower() not in EXT and path.name not in (".env", ".env.example"):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        new = replace_text(raw)
        if new != raw:
            path.write_text(new, encoding="utf-8", newline="\n" if path.suffix != ".md" else None)
            # preserve: write with utf-8
            path.write_text(new, encoding="utf-8")
            changed.append(str(path.relative_to(ROOT)))
    return changed


REMOTE_ENV = """
set -e
cd /opt/agentlink
python3 - <<'PY'
from pathlib import Path
repl = {
  "1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW": "1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW",
  "1.2.156.3088.1.BUPT.2HY2P9.21P09A.N3GL7K.11NO": "1.2.156.3088.1.BUPT.2HY2P9.21P09A.N3GL7K.11NO",
  "1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS": "1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS",
  "1.2.156.3088.1.BUPT.2HY2P9.NH4J42.CV501K.0U11": "1.2.156.3088.1.BUPT.2HY2P9.NH4J42.CV501K.0U11",
  "1.2.156.3088.1.BUPT.2HY2P9.SHDUXP.AKGA0G.0768": "1.2.156.3088.1.BUPT.2HY2P9.SHDUXP.AKGA0G.0768",
  "1.2.156.3088.1.BUPT.2HY2P9.8R39K3.RQIABQ.1ABF": "1.2.156.3088.1.BUPT.2HY2P9.8R39K3.RQIABQ.1ABF",
}
tokens = {
  "ODIFWZ":"ODIFWZ","FN5REA":"FN5REA","21P09A":"21P09A","N3GL7K":"N3GL7K",
  "ZBD999":"ZBD999","NQXAR6":"NQXAR6","NH4J42":"NH4J42","CV501K":"CV501K",
  "SHDUXP":"SHDUXP","AKGA0G":"AKGA0G","8R39K3":"8R39K3","RQIABQ":"RQIABQ",
}
paths = list(Path('/opt/agentlink').glob('.env'))
paths += list(Path('/etc/agentlink').glob('*.env'))
paths += list(Path('/opt/agentlink/acs').glob('*.acs.json'))
# also commerce discovery if synced
for extra in [
  '/opt/agentlink/commerce/discovery.py',
  '/opt/agentlink/commerce/buyer_tools/service.py',
  '/opt/agentlink/commerce/rfq_bridge.py',
]:
  p=Path(extra)
  if p.is_file():
    paths.append(p)
n=0
for p in paths:
  if not p.is_file():
    continue
  t=p.read_text(encoding='utf-8', errors='ignore')
  o=t
  for a,b in repl.items():
    t=t.replace(a,b)
  for a,b in tokens.items():
    t=t.replace(a,b)
  if t!=o:
    p.write_text(t, encoding='utf-8')
    n+=1
    print('updated', p)
print('files', n)
PY
grep -E '^(BUYER_|SUPPLIER_|LOGISTICS_).*AIC=' /opt/agentlink/.env || true
"""


def remote_apply(host: str, *, password: str | None = None, key: bool = False) -> str:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if key:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = password or PW
    c.connect(**kw)
    # upload critical code files that contain token matching
    sftp = c.open_sftp()
    for rel in (
        "commerce/discovery.py",
        "commerce/buyer_tools/service.py",
        "commerce/auction_suitability.py",
        "commerce/choice_actions.py",
        "commerce/chat_buyer_wit.py",
        "docs/aic码.md",
        "acs/buyer-agent-a.acs.json",
        "acs/buyer-agent-b.acs.json",
        "acs/logistics-agent.acs.json",
        "acs/supplier-agent-a.acs.json",
        "acs/supplier-agent-b.acs.json",
        "acs/supplier-agent-c.acs.json",
    ):
        local = ROOT / rel
        if local.is_file():
            remote = f"/opt/agentlink/{rel}"
            try:
                sftp.put(str(local), remote)
                print(f"put {host}:{rel}", flush=True)
            except Exception as exc:
                print(f"skip put {rel}: {exc}", flush=True)
    sftp.close()
    _, o, e = c.exec_command(REMOTE_ENV, timeout=120, get_pty=True)
    out = (o.read() + e.read()).decode("utf-8", errors="replace")
    # restart agent units
    restart = r"""
systemctl restart agentlink-buyer-a agentlink-buyer-b agentlink-logistics 2>/dev/null || true
systemctl restart agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c 2>/dev/null || true
sleep 3
systemctl is-active agentlink-buyer-a agentlink-buyer-b agentlink-logistics 2>/dev/null || true
systemctl is-active agentlink-supplier-a agentlink-supplier-b agentlink-supplier-c 2>/dev/null || true
for p in 8010 8011 8012 8013 8014 8015; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 2 https://127.0.0.1:$p/health || true)
  echo ":$p=$code"
done
"""
    _, o2, e2 = c.exec_command(restart, timeout=90, get_pty=True)
    out2 = (o2.read() + e2.read()).decode("utf-8", errors="replace")
    c.close()
    return out + "\n" + out2


def main() -> None:
    print("==== local replace ====", flush=True)
    changed = local_replace()
    for c in changed:
        print(" ", c)
    print(f"local files changed: {len(changed)}", flush=True)

    # ensure aic doc exact
    (ROOT / "docs" / "aic码.md").write_text(
        """# 智能体 AIC 码

| 智能体 | AIC |
| --- | --- |
| 采联采购智能体A (`buyer-a`) | `1.2.156.3088.1.BUPT.2HY2P9.ODIFWZ.FN5REA.0UJW` |
| 采联采购智能体B (`buyer-b`) | `1.2.156.3088.1.BUPT.2HY2P9.21P09A.N3GL7K.11NO` |
| 采联物流智能体 (`logistics`) | `1.2.156.3088.1.BUPT.2HY2P9.ZBD999.NQXAR6.0ZZS` |
| 采联供应商智能体A (`supplier-a`) | `1.2.156.3088.1.BUPT.2HY2P9.NH4J42.CV501K.0U11` |
| 采联供应商智能体B (`supplier-b`) | `1.2.156.3088.1.BUPT.2HY2P9.SHDUXP.AKGA0G.0768` |
| 采联供应商智能体C (`supplier-c`) | `1.2.156.3088.1.BUPT.2HY2P9.8R39K3.RQIABQ.1ABF` |
""",
        encoding="utf-8",
    )

    print("==== Tencent ====", flush=True)
    print(remote_apply("81.70.46.119", key=True))
    print("==== Aliyun ====", flush=True)
    print(remote_apply("39.105.20.113", password=PW))


if __name__ == "__main__":
    main()
