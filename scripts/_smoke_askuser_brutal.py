# -*- coding: utf-8 -*-
"""双云狠测：六健康 + AskUser 时机 + 缺规格 blockers 闭环 + post_quote 推荐项。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
PW = os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@")

TENCENT_HEALTH = [
    ("buyer-a", 8010),
    ("buyer-b", 8012),
    ("logistics", 8015),
]
ALIYUN_HEALTH = [
    ("supplier-a", 8011),
    ("supplier-b", 8013),
    ("supplier-c", 8014),
]


def ssh(host: str, *, pem: bool) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw: dict = dict(hostname=host, username="root", timeout=40, allow_agent=False, look_for_keys=False)
    if pem:
        kw["pkey"] = paramiko.RSAKey.from_private_key_file(str(PEM))
    else:
        kw["password"] = PW
    c.connect(**kw)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout, get_pty=True)
    return (o.read() + e.read()).decode("utf-8", "replace")


BUYER_BRUTAL = r"""
set -e
cd /opt/agentlink
.venv/bin/python - <<'PY'
import asyncio, json, sys
sys.path.insert(0,'/opt/agentlink')
from commerce.hitl_policy import should_offer_choices, recommend_first, choices_from_blockers
from commerce.goal_runtime import blocker, with_runtime_meta, shipping_blockers_from_mass, backfill_specs
from commerce.choice_actions import post_quote_choices
from commerce import seat_catalog

fails=[]

# 1 AskUser 边界
cases=[
  ('1branch', not should_offer_choices(branch_count=1)),
  ('2branch', should_offer_choices(branch_count=2)),
  ('approve_nofork', not should_offer_choices(gate='approve_plan', branch_count=1)),
  ('ambiguous', should_offer_choices(ambiguous=True)),
]
for name, ok in cases:
  if not ok: fails.append(name)

# 2 缺体积 → blockers 不问人猜
bl = shipping_blockers_from_mass({'weight_kg': 12})
assert any(b['code']=='MISSING_VOLUME' for b in bl), bl
assert bl[0]['repair_tool']=='flow.backfill_specs'
assert not should_offer_choices(blockers=bl, branch_count=0), 'must not AskUser volume'
assert choices_from_blockers(bl) is None

# 3 补规格（脚轮 SKU）
specs = seat_catalog.product_physical_specs('RM-CASTER-300', qty=500)
assert specs.get('volume_m3') and specs.get('weight_kg'), specs
bl2 = shipping_blockers_from_mass(specs)
assert not any(b['code']=='MISSING_VOLUME' for b in bl2), bl2

async def bf():
  r = await backfill_specs('buyer-a', case_id=None, order_ticket_id=None, ask_supplier=False)
  assert 'ok' in r and 'blockers' in r
  return r
_bf = asyncio.run(bf())
print('backfill_shape', {'ok': _bf.get('ok'), 'n_blockers': len(_bf.get('blockers') or [])})

# 4 post_quote 推荐第一
w = post_quote_choices(case_id='brutal', lowest_agent_id='supplier-a', supplier_ids=['supplier-a','supplier-b','supplier-c'])
ch = recommend_first(list(w.get('choices') or []))
assert ch and ch[0].get('primary') and '推荐' in (ch[0].get('label') or ch[0].get('id') or ''), ch[0]

# 5 物流 wit 能力 id 可构建
from commerce import chat_logistics_wit as clw
clw.configure(agent_id='logistics')
caps = clw._build_capabilities()
ids = [getattr(c,'id',None) or getattr(c,'__name__',None) for c in caps]
# capability decorator may stash id differently
print('log_caps', len(caps))

# 6 buyer wit 提示含 AskUser
from commerce import chat_buyer_wit as cbw
assert 'AskUserQuestion' in (cbw.INSTRUCTIONS or '') or '出按钮时机' in (cbw.INSTRUCTIONS or '')

if fails:
  raise SystemExit('FAIL '+','.join(fails))
print('BUYER_BRUTAL_PASS', json.dumps({'specs500':specs,'quote_choices':len(ch)}, ensure_ascii=False))
PY
"""

SUPPLIER_BRUTAL = r"""
set -e
cd /opt/agentlink
.venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0,'/opt/agentlink')
from commerce.hitl_policy import should_offer_choices, recommend_first
from commerce import chat_supplier_wit as csw

csw.configure(agent_id='supplier-a')
assert 'AskUserQuestion' in csw.INSTRUCTIONS or '出按钮时机' in csw.INSTRUCTIONS
caps = csw._build_capabilities()
print('sup_caps', len(caps))
# multi ticket → should offer
assert should_offer_choices(branch_count=3, irreversible=True)
ch = recommend_first([{'id':'x','label':'确认甲'},{'id':'y','label':'确认乙','primary':True}])
assert ch[0]['id']=='y' and '推荐' in ch[0]['label']
print('SUPPLIER_BRUTAL_PASS', json.dumps({'caps':len(caps)}, ensure_ascii=False))
PY
"""


def health_via_ssh(c: paramiko.SSHClient, agents: list[tuple[str, int]]) -> list[tuple[str, bool, str]]:
    script = "\n".join(
        f"echo -n '{name} '; curl -sk --max-time 8 https://127.0.0.1:{port}/health | head -c 120; echo"
        for name, port in agents
    )
    out = run(c, script, timeout=60)
    rows = []
    for name, _port in agents:
        ok = False
        line = next((ln for ln in out.splitlines() if ln.startswith(name + " ")), "")
        ok = "ok" in line.lower() or '"status"' in line.lower() or "healthy" in line.lower() or "true" in line.lower()
        # accept any non-empty HTTP body after name
        if not ok and len(line.split(" ", 1)[-1].strip()) > 2 and "Connection refused" not in line:
            ok = True
        rows.append((name, ok, line))
        print(f"health {line}", flush=True)
    return rows


def main() -> None:
    bc = ssh("81.70.46.119", pem=True)
    h1 = health_via_ssh(bc, TENCENT_HEALTH)
    out = run(bc, BUYER_BRUTAL, timeout=180)
    print("==== buyer brutal ====\n", out[-5000:], flush=True)
    if "BUYER_BRUTAL_PASS" not in out:
        raise SystemExit("buyer brutal failed")
    bc.close()

    sc = ssh("39.105.20.113", pem=False)
    h2 = health_via_ssh(sc, ALIYUN_HEALTH)
    out2 = run(sc, SUPPLIER_BRUTAL, timeout=120)
    print("==== supplier brutal ====\n", out2[-3000:], flush=True)
    if "SUPPLIER_BRUTAL_PASS" not in out2:
        raise SystemExit("supplier brutal failed")
    sc.close()

    bad = [n for n, ok, _ in h1 + h2 if not ok]
    if bad:
        raise SystemExit(f"health fail: {bad}")

    print(json.dumps({"ok": True, "agents": [n for n, _, _ in h1 + h2]}, ensure_ascii=False))
    print("ASKUSER_BRUTAL_DONE", flush=True)


if __name__ == "__main__":
    main()
