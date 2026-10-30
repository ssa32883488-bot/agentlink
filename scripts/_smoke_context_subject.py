# -*- coding: utf-8 -*-
"""冒烟：对话窗不得把脚轮旧案串进扶手主体。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commerce import chat_sessions as cs
from commerce import procurement_case as pc
from commerce.buyer_tools.service import BuyerToolService
from commerce.flow_service import create_from_brief


def main() -> int:
    agent = "buyer-a-test-subject"
    # 旧脚轮案
    caster = create_from_brief(product_name="重型脚轮（RM-CASTER-300）", quantity=500, note="old")
    # 新对话窗
    th = cs.create_thread(agent, title="扶手采购窗")
    tid = th["id"]
    assert cs.thread_bound_case_id(agent, tid) is None

    # 绑定扶手案到本窗
    arm = create_from_brief(product_name="扶手总成（RM-ARMREST）", quantity=500, note="arm")
    cs.bind_thread_case(agent, tid, arm["case_id"], product_name="扶手总成（RM-ARMREST）")
    assert cs.thread_bound_case_id(agent, tid) == arm["case_id"]

    # 共享事实提示：无物料的裸数量应标注需核对
    cs.upsert_shared_fact(agent, "净采购量", 500, tags=["shared", "关键"], source_thread_id=tid)
    block = cs.shared_facts_prompt_block(agent, subject_product="扶手总成（RM-ARMREST）")
    assert "需向用户确认" in block or "未绑定物料" in block

    # 产品不一致 → discover 应新开案（同步测 mismatch 辅助）
    svc = BuyerToolService()
    assert svc._product_mismatch(pc.get_case(caster["case_id"]), "扶手总成（RM-ARMREST）") is True
    assert svc._product_mismatch(pc.get_case(arm["case_id"]), "扶手总成（RM-ARMREST）") is False
    assert svc._product_mismatch(pc.get_case(arm["case_id"]), "RM-ARMREST") is False

    print("PASS", "caster", caster["case_id"], "arm", arm["case_id"], "thread", tid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
