# -*- coding: utf-8 -*-
"""把一次性 diag/fix/peek/probe/临时 deploy 挪到 scripts/_archive/20261030/，精简工作区。"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
DEST = ROOT / "_archive" / "20261030"

# 保留：当前主路径 deploy/smoke/e2e/purge/bench + 本归档器
KEEP_PREFIXES = (
    "_archive",
    "_archive_oneoff",
    "_deploy_goal_runtime",
    "_deploy_quote_bargain_phase",
    "_deploy_qty_specs_fix",
    "_deploy_dialog_flow",
    "_deploy_buyer_logistics",
    "_deploy_ui_static",
    "_deploy_nofloor_java_jars",
    "_deploy_office",
    "_smoke_",
    "_e2e_",
    "_bench_",
    "_purge_",
    "smoke_",
    "e2e_",
)

# 明确归档：diag/fix/peek/probe/tmp/旧阶段 deploy
ARCHIVE_GLOBS = (
    "_diag_*.py",
    "_fix_*.py",
    "_peek_*.py",
    "_probe_*.py",
    "_tmp_*.py",
    "_check_*.py",
    "_unstick_*.py",
    "_strip_*.py",
    "_switch_*.py",
    "_sync_java_*.py",
    "_verify_*.py",
    "_align_*.py",
    "_apply_*.py",
    "_assert_*.py",
    "_find_*.py",
    "_inspect_*.py",
    "_ping_*.py",
    "_restart_supplier_erp.py",
    "_deploy_rm_hitl_prompt.py",
    "_deploy_bargain_phase.py",
    "_deploy_bargain_promo.py",
    "_deploy_latency_opt.py",
    "_deploy_auction_rpc_fallback.py",
    "_deploy_discovery_*.py",
    "_deploy_aic_*.py",
    "_deploy_amp_*.py",
    "_deploy_buyer_v1_*.py",
    "_deploy_catalog_*.py",
    "_deploy_choice_*.py",
    "_deploy_context_*.py",
    "_deploy_cushion_*.py",
    "_deploy_full_*.py",
    "_deploy_merchant.py",
    "_deploy_per_agent_*.py",
    "_deploy_review_*.py",
    "_deploy_status_*.py",
    "_deploy_supplier_*.py",
    "_deploy_table_*.py",
    "_deploy_ui_partner_*.py",
    "_go_live_*.py",
    "_finish_*.py",
    "_replace_*.py",
    "_smoke_bargain_phase_remote.py",
    "_smoke_qty_specs.py",
)


def kept(name: str) -> bool:
    for p in KEEP_PREFIXES:
        if name.startswith(p) or name == p + ".py":
            # still archive if matches ARCHIVE and not core keep
            if p in ("_smoke_", "_e2e_", "_bench_", "_purge_", "smoke_", "e2e_"):
                return True
            if p.startswith("_deploy_goal") or p.startswith("_deploy_quote") or p.startswith("_deploy_qty"):
                return True
            if p.startswith("_deploy_dialog") or p.startswith("_deploy_buyer_logistics"):
                return True
            if p.startswith("_deploy_ui_static") or p.startswith("_deploy_nofloor") or p.startswith("_deploy_office"):
                return True
            if p.startswith("_archive"):
                return True
    return False


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    moved = []
    for pattern in ARCHIVE_GLOBS:
        for path in ROOT.glob(pattern):
            if not path.is_file():
                continue
            if path.name.startswith("_archive"):
                continue
            # keep current core smokes
            if path.name in {
                "_smoke_quote_bargain_local.py",
                "_e2e_fast_two_scenarios.py",
                "_e2e_two_scenarios.py",
                "_purge_chat_tickets.py",
                "_bench_auction_latency.py",
                "_deploy_goal_runtime.py",
                "_deploy_quote_bargain_phase.py",
                "_deploy_qty_specs_fix.py",
                "_deploy_dialog_flow.py",
                "_deploy_buyer_logistics.py",
                "_deploy_ui_static.py",
                "_deploy_nofloor_java_jars.py",
                "_deploy_office.py",
            }:
                continue
            dest = DEST / path.name
            shutil.move(str(path), str(dest))
            moved.append(path.name)
    print(f"archived {len(moved)} -> {DEST}")
    for n in moved[:40]:
        print(" ", n)
    if len(moved) > 40:
        print(f"  ... +{len(moved)-40} more")


if __name__ == "__main__":
    main()
