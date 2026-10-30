"""采购 V1 Tools 业务实现（ADP/AIP + 记忆）。"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from agentlink_runtime.aip_client_util import aip_start_structured
from agentlink_runtime.aip_payload import wrap_business
from agents.buyer_a.graph import compare_quotes
from commerce import buyer_service as bs
from commerce import flow_service as fs
from commerce import procurement_case as pc
from commerce.buyer_tools.memory_store import MemoryStore
from commerce.buyer_tools.schemas import (
    CandidateOut,
    DiscoverIn,
    DiscoverOut,
    FreightQuote,
    PartnerDialogIn,
    PartnerDialogOut,
    PartnerRef,
    QuoteRow,
    RfqBatchIn,
    RfqBatchOut,
    UiHintShortlist,
)
from commerce.choice_actions import post_quote_choices
from commerce.choice_actions import post_quote_choices
from commerce.discovery import discover_suppliers
from commerce.hitl_gate import make_hitl
from commerce.merchant import buyer_destination
from commerce.progress import report
from commerce.rfq_bridge import SUPPLIER_MAP


def _buyer_agent_id() -> str:
    return (os.getenv("BUYER_AGENT_ID") or "buyer-a").strip()


def LEADER_AIC() -> str:
    aid = _buyer_agent_id()
    if aid == "buyer-b":
        return os.getenv("BUYER_B_AIC") or os.getenv("BUYER_A_AIC") or "buyer-b-local-aic"
    return os.getenv("BUYER_A_AIC") or "buyer-a-local-aic"


def _rfq_destination() -> dict[str, Any]:
    d = buyer_destination(_buyer_agent_id())
    return {"postal_code": d["postal_code"], "city": d.get("city"), "address": d.get("address")}


def _ensure_partner_specs(
    agent_id: str | None, product_name: str | None, specs: dict[str, Any] | None
) -> dict[str, Any]:
    """供应 B 要求 material/color；按物料给合理默认，避免 clarify 卡在 awaiting-input。"""
    out = dict(specs or {})
    if (agent_id or "") != "supplier-b":
        return out
    pname = str(product_name or "")
    if any(k in pname for k in ("坐垫", "海绵", "FOAM", "foam")):
        out.setdefault("material", "memory-foam")
        out.setdefault("color", "black")
    elif any(k in pname for k in ("面料", "FABRIC", "fabric")):
        out.setdefault("material", "fabric")
        out.setdefault("color", "black")
    else:
        out.setdefault("material", "standard")
        out.setdefault("color", "black")
    return out


class BuyerToolService:
    def __init__(self) -> None:
        self.memory = MemoryStore(agent_id=os.getenv("BUYER_AGENT_ID") or "buyer-a")
        self._active_case: str | None = None

    def refresh_agent(self) -> None:
        aid = os.getenv("BUYER_AGENT_ID") or "buyer-a"
        self.memory = MemoryStore(agent_id=aid)

    def set_active_case(self, case_id: str | None) -> None:
        self._active_case = case_id

    def active_case_id(self) -> str | None:
        return self._active_case

    def _resolve_case(self, case_id: str | None) -> str | None:
        # 只认显式 case_id 或本进程活跃案；禁止回落「全库最新一案」（会串物料主体）
        cid = (case_id or self._active_case or "").strip() or None
        if cid:
            self._active_case = cid
            return cid
        return None

    def _partner_from_candidate(self, c: dict[str, Any]) -> PartnerRef:
        return PartnerRef(
            agent_id=c.get("agent_id"),
            aic=str(c.get("aic") or ""),
            name=c.get("name"),
            endpoint=str(c.get("endpoint") or ""),
            skills=list(c.get("skills") or []),
        )

    def _case_can_discover(self, case: dict[str, Any] | None) -> bool:
        if not case or case.get("voided"):
            return False
        # 仅 ALLOWED 中能迁入/停留 DISCOVERING 的状态
        return str(case.get("state") or "") in ("DRAFT", "DISCOVERING", "SHORTLIST_PENDING")

    @staticmethod
    def _product_mismatch(case: dict[str, Any] | None, product_name: str) -> bool:
        if not case or not product_name:
            return False
        brief = case.get("brief") or {}
        # 组合需求案：只要新传入文本与已有 lines/品名有交集，不算串案
        if brief.get("combo") or brief.get("lines"):
            blob = " ".join(
                [
                    str(brief.get("product_name") or ""),
                    *[
                        f"{x.get('sku','')} {x.get('name','')}"
                        for x in (brief.get("lines") or [])
                        if isinstance(x, dict)
                    ],
                ]
            )
            want = str(product_name or "").strip()
            if want and (want in blob or any(tok and tok in blob for tok in re.split(r"[+＋、,，/与和]+", want) if len(tok.strip()) >= 2)):
                return False
        brief_name = str(brief.get("product_name") or "").strip()
        want = str(product_name or "").strip()
        if not brief_name or not want:
            return False
        # 任一方向包含即视为同主体（兼容「扶手总成 / RM-ARMREST」）
        return want not in brief_name and brief_name not in want

    @staticmethod
    def _normalize_lines(raw_lines: list[Any] | None, *, product_name: str, quantity: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in raw_lines or []:
            if hasattr(row, "model_dump"):
                row = row.model_dump()
            if not isinstance(row, dict):
                continue
            sku = str(row.get("sku") or row.get("product_name") or "").strip()
            name = str(row.get("name") or sku).strip()
            if not sku and not name:
                continue
            try:
                qty = float(row.get("qty") if row.get("qty") is not None else row.get("quantity") or 1)
            except (TypeError, ValueError):
                qty = 1.0
            out.append(
                {
                    "sku": sku or name,
                    "name": name or sku,
                    "qty": qty,
                    "unit": str(row.get("unit") or "件"),
                    "specs": dict(row.get("specs") or {}),
                }
            )
        if out:
            return out
        pname = (product_name or "").strip()
        if not pname:
            return []
        # 尝试拆「A+B / A和B」为多行（数量先均摊到 quantity，调用方应用 lines 明确数量）
        parts = [p.strip() for p in re.split(r"[+＋、,，/]|与|和", pname) if p.strip()]
        if len(parts) >= 2:
            return [
                {"sku": p, "name": p, "qty": float(quantity), "unit": "件", "specs": {}}
                for p in parts
            ]
        return [{"sku": pname, "name": pname, "qty": float(quantity), "unit": "件", "specs": {}}]

    @staticmethod
    def _brief_lines(brief: dict[str, Any] | None) -> list[dict[str, Any]]:
        brief = brief or {}
        lines = brief.get("lines")
        if isinstance(lines, list) and lines:
            return [x for x in lines if isinstance(x, dict)]
        return [
            {
                "sku": str(brief.get("product_name") or "物料"),
                "name": str(brief.get("product_name") or "物料"),
                "qty": float(brief.get("quantity") or 1),
                "unit": "件",
                "specs": dict(brief.get("specifications") or {}),
            }
        ]

    @staticmethod
    def _enrich_merchant(agent_id: str | None, row: dict[str, Any]) -> dict[str, Any]:
        from commerce.merchant import profile as merchant_profile

        aid = str(agent_id or "")
        p = merchant_profile(aid) if aid else {}
        trade = str(p.get("trade_name") or p.get("organization") or row.get("name") or aid)
        addr = str(p.get("address") or "")
        city = str(p.get("city") or "")
        biz = str(p.get("notes") or p.get("strategy_tag") or "")
        return {
            **row,
            "trade_name": trade,
            "address": addr,
            "city": city,
            "business": biz,
            "name": trade or row.get("name") or aid,
            "match_reason": row.get("match_reason")
            or (f"{city}·{biz}" if city or biz else "平台 ADP 命中"),
        }

    async def discover_suppliers_tool(self, raw: dict[str, Any] | None = None) -> dict[str, Any]:
        inp = DiscoverIn.model_validate(raw or {})
        cid = self._resolve_case(inp.case_id)
        existing = pc.get_case(cid) if cid else None
        lines = self._normalize_lines(
            list(inp.lines or []),
            product_name=inp.product_name,
            quantity=inp.quantity,
        )
        pname = (inp.product_name or "").strip()
        if not pname and lines:
            pname = " + ".join(f"{x['name']}×{int(x['qty'])}" for x in lines)
        # 物料主体不一致 → 强制新开案，禁止把脚轮案续成扶手（或反之）
        if existing and self._product_mismatch(existing, pname):
            existing = None
            cid = None
        if not pname:
            return {
                "ok": False,
                "case_id": cid,
                "source": "validation",
                "candidates": [],
                "error": {"code": "PRODUCT_REQUIRED", "message": "product_name 或 lines 必填，须与本窗对话主体一致"},
            }
        if not cid or not self._case_can_discover(existing):
            # 无案、主体不符或旧案已终态 → 新开采购案（可含组合 lines）
            case = fs.create_from_brief(
                product_name=pname,
                quantity=inp.quantity,
                rated_load_kg_min=inp.rated_load_kg_min,
                note="via discover.suppliers",
                lines=lines if len(lines) >= 2 else None,
            )
            cid = case["case_id"]
            self._active_case = cid
        elif lines and len(lines) >= 2:
            # 已有可发现案：补写组合行，避免未询价就拆案
            brief = dict((existing or {}).get("brief") or {})
            if not brief.get("lines"):
                brief["lines"] = lines
                brief["combo"] = True
                brief["product_name"] = pname
                pc.update_case(cid, brief=brief)
        # 发现查询：组合需求用自然语言，不拆案
        discover_q = (inp.query or "").strip()
        if not discover_q:
            if len(lines) >= 2:
                names = "和".join(str(x.get("name") or x.get("sku")) for x in lines)
                discover_q = f"我需要购买{names}，哪家供应商符合我的需求？"
            else:
                discover_q = f"供应 {pname}"
        case = await fs.step_discover(cid, discover_q, bypass_cache=inp.refresh)
        meta = case.get("discovery_meta") or {}
        candidates_out: list[CandidateOut] = []
        stored: list[dict[str, Any]] = []
        for i, c in enumerate((case.get("candidates") or [])[: inp.limit]):
            cand_id = f"cand-{cid[-6:]}-{i+1}"
            row = {
                **c,
                "candidate_id": cand_id,
                "match_reason": c.get("match_reason")
                or (f"匹配技能 {c.get('acs', {}).get('_matched_skill')}" if isinstance(c.get("acs"), dict) else "平台 ADP 命中"),
                "source_label": c.get("source_label") or "平台发现",
            }
            row = self._enrich_merchant(c.get("agent_id"), row)
            stored.append(row)
            candidates_out.append(
                CandidateOut(
                    candidate_id=cand_id,
                    agent_id=c.get("agent_id"),
                    aic=str(c.get("aic") or ""),
                    name=str(row.get("name") or c.get("name") or c.get("agent_id") or ""),
                    endpoint=str(c.get("endpoint") or ""),
                    skills=list(c.get("skills") or []),
                    matched_skill=(c.get("acs") or {}).get("_matched_skill")
                    if isinstance(c.get("acs"), dict)
                    else None,
                    match_reason=str(row.get("match_reason") or ""),
                    source_label=row["source_label"],
                    trade_name=row.get("trade_name"),
                    address=row.get("address"),
                    city=row.get("city"),
                    business=row.get("business"),
                )
            )
        pc.update_case(
            cid,
            candidates=stored,
            discovery_meta={**meta, "ui_candidates": [x.model_dump() for x in candidates_out]},
            hitl_pending=make_hitl(
                "confirm_shortlist",
                "请在表单中勾选要询价的供应商（1–5 家）；组合需求先统一询价，稍后再决定是否拆单",
                options=["approve", "edit", "reject"],
            ),
        )
        self.memory.record(
            cid,
            event="discover_done",
            payload={"source": meta.get("source"), "n": len(candidates_out)},
        )
        self.memory.inject(
            cid,
            [{"key": "last_discover_candidates", "value": [x.model_dump() for x in candidates_out], "tags": ["discover"]}],
        )
        source = str(meta.get("source") or ("platform_adp" if candidates_out else "platform_adp_empty"))
        out = DiscoverOut(
            ok=True,
            case_id=cid,
            source=source,
            discovery_url=meta.get("discovery_url"),
            elapsed_ms=meta.get("elapsed_ms"),
            platform_error=meta.get("platform_error"),
            candidates=candidates_out,
            ui_hint=UiHintShortlist(
                title="请确认询价短名单（平台发现）",
                min_select=1,
                max_select=min(5, max(1, len(candidates_out) or 1)),
            )
            if candidates_out
            else None,
            hitl={
                "gate": "confirm_shortlist",
                "prompt": "请勾选供应商后确认询价" if candidates_out else "平台未命中供应商，可换查询词再发现",
            },
        )
        dumped = out.model_dump()
        dumped["presentation_hint"] = (
            "向用户展示候选时必须用 Markdown 表格"
            "（列：供应商|厂名/主营|地址|匹配说明|来源），并提示下方勾选表单；"
            "组合需求不要拆成两套短名单；禁止散文罗列。"
        )
        return dumped

    def _resolve_selected(
        self, case: dict[str, Any], selected: list[str | dict[str, Any]]
    ) -> list[dict[str, Any]]:
        by_id = {str(c.get("candidate_id")): c for c in (case.get("candidates") or []) if c.get("candidate_id")}
        by_agent = {str(c.get("agent_id")): c for c in (case.get("candidates") or []) if c.get("agent_id")}
        out: list[dict[str, Any]] = []
        for item in selected[:5]:
            if isinstance(item, dict):
                out.append(item)
                continue
            key = str(item).strip()
            if key in by_id:
                out.append(by_id[key])
            elif key in by_agent:
                out.append(by_agent[key])
            elif key in SUPPLIER_MAP:
                meta = SUPPLIER_MAP[key]
                out.append(
                    {
                        "agent_id": key,
                        "aic": meta["aic"],
                        "endpoint": meta["url"],
                        "name": key,
                        "candidate_id": key,
                    }
                )
        return out

    async def rfq_send_batch(self, raw: dict[str, Any] | None = None) -> dict[str, Any]:
        inp = RfqBatchIn.model_validate(raw or {})
        cid = self._resolve_case(inp.case_id)
        if not cid:
            return RfqBatchOut(ok=False, case_id="", error={"code": "NO_CASE", "message": "尚无采购案"}).model_dump()
        case = pc.get_case(cid)
        if not case:
            return RfqBatchOut(ok=False, case_id=cid, error={"code": "NO_CASE", "message": "案件不存在"}).model_dump()
        partners = self._resolve_selected(case, list(inp.selected))
        if not partners:
            return RfqBatchOut(
                ok=False, case_id=cid, error={"code": "VALIDATION", "message": "未解析到有效供应商（1–5）"}
            ).model_dump()
        if len(partners) > 5:
            partners = partners[:5]

        # 确认短名单（幂等）
        agent_ids = []
        for p in partners:
            aid = p.get("agent_id")
            if not aid or not str(aid).startswith("supplier-"):
                # 尝试归一
                aic = str(p.get("aic") or "")
                if any(m in aic for m in ("WP4OOG", "NH4J42")):
                    aid = "supplier-a"
                elif any(m in aic for m in ("6CW2XR", "SHDUXP")):
                    aid = "supplier-b"
                elif any(m in aic for m in ("1VQMIO", "8R39K3")):
                    aid = "supplier-c"
                else:
                    aid = f"partner-{aic[-6:] or uuid4().hex[:6]}"
                p["agent_id"] = aid
            agent_ids.append(aid)
            # 平台 ADP 可能仍给旧 AIC：强制用本域 env（证书 CN）覆盖
            if aid in SUPPLIER_MAP:
                p["aic"] = SUPPLIER_MAP[aid]["aic"]
                p["endpoint"] = SUPPLIER_MAP[aid]["url"]

        try:
            fs.step_confirm_shortlist(cid, [a for a in agent_ids if a in SUPPLIER_MAP] or agent_ids[:1])
        except ValueError:
            # 非标准 agent_id：直接写入 shortlist
            pc.transition(
                cid,
                "SOURCING",
                event="shortlist_manual",
                patch={"shortlist": partners, "shortlist_confirmed": True, "hitl_pending": None},
            )

        brief = case["brief"]
        demand_lines = self._brief_lines(brief)
        multi = len(demand_lines) >= 2
        deadline = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        report(
            f"rfq.send_batch · 并行 {len(partners)} 家"
            + (f" × {len(demand_lines)} 行物料" if multi else "")
            + "询价",
            phase="aip",
        )

        async def _one_line(partner: dict[str, Any], line: dict[str, Any]) -> QuoteRow:
            pref = self._partner_from_candidate(partner)
            label = pref.name or pref.agent_id or pref.aic[-8:]
            line_name = str(line.get("name") or line.get("sku") or brief.get("product_name"))
            line_sku = str(line.get("sku") or line_name)
            report(f"经 AIP 向「{label}」询价 {line_name}…", phase="aip")
            specs = _ensure_partner_specs(
                partner.get("agent_id"),
                line_name,
                dict(line.get("specs") or brief.get("specifications") or {}),
            )
            specs = {**specs, "sku": line_sku}
            try:
                qty = float(line.get("qty") or brief.get("quantity") or 1)
            except (TypeError, ValueError):
                qty = float(brief.get("quantity") or 1)
            qty = max(int(qty), 200 if partner.get("agent_id") == "supplier-b" and "FABRIC" in line_sku.upper() else 1)
            dest = _rfq_destination()
            envelope = wrap_business(
                "agentlink.quote_request",
                cid,
                {
                    "purchase_request_id": brief.get("purchase_request_id"),
                    "version": 1,
                    "product_name": line_name,
                    "specifications": specs,
                    "quantity": qty,
                    "currency": "CNY",
                    "tax_included_required": True,
                    "delivery_deadline": (brief.get("delivery") or {}).get("deadline"),
                    "quality_requirements": brief.get("quality_requirements") or [],
                    "quote_deadline": deadline,
                    "need_bargain_room": False,
                    "need_freight": False,
                    "destination": dest,
                    "postal_code": dest["postal_code"],
                },
            )
            try:
                out = await asyncio.wait_for(
                    aip_start_structured(
                        partner_url=pref.endpoint,
                        leader_aic=LEADER_AIC(),
                        partner_aic=pref.aic,
                        session_id=f"batch-rfq-{cid}-{partner.get('agent_id') or uuid4().hex[:6]}-{line_sku[-8:]}",
                        envelope=envelope,
                        local_agent_id=_buyer_agent_id(),
                    ),
                    timeout=max(inp.timeout_ms / 1000.0, 5.0),
                )
            except TimeoutError:
                return QuoteRow(partner=pref, status="timeout", error=f"{line_name}：询价超时")
            except Exception as exc:  # noqa: BLE001
                return QuoteRow(partner=pref, status="error", error=f"{line_name}：{exc}")

            state = str(out.get("state") or "").lower()
            env = out.get("envelope") or {}
            pay = env.get("payload") if isinstance(env, dict) else {}
            if not isinstance(pay, dict):
                pay = {}
            msg = str(out.get("message") or pay.get("reject_reason") or pay.get("note") or "").strip()
            if state in {"rejected", "failed"} or (not pay.get("unit_price") and not env):
                return QuoteRow(
                    partner=pref,
                    status="error",
                    error=msg or f"{line_name}：供应侧拒绝报价（state={state or 'empty'}）",
                    task_id=str(out.get("task_id") or "") or None,
                )
            pay.setdefault("supplier_agent_id", partner.get("agent_id"))
            unit = pay.get("unit_price")
            if unit is None:
                return QuoteRow(
                    partner=pref,
                    status="error",
                    error=msg or f"{line_name}：未返回单价（可能目录无此物料）",
                    task_id=str(out.get("task_id") or "") or None,
                )
            quoted_sku = str((pay.get("product") or {}).get("sku") or pay.get("sku") or "").upper()
            quoted_name = str((pay.get("product") or {}).get("name") or pay.get("name") or "")
            from agents.supplier_common.catalog_price import normalize_sku

            want_sku = normalize_sku(line_sku) or normalize_sku(line_name)
            if want_sku and quoted_sku and quoted_sku != want_sku:
                return QuoteRow(
                    partner=pref,
                    status="error",
                    error=f"回执物料不符：请求 {want_sku}/{line_name}，实报 {quoted_sku}/{quoted_name}",
                    task_id=str(out.get("task_id") or "") or None,
                )
            try:
                goods = float(unit) * float(qty)
            except (TypeError, ValueError):
                return QuoteRow(partner=pref, status="error", error=f"{line_name}：单价无效 {unit}")
            freight_amt = pay.get("freight_amount")
            if freight_amt is None and isinstance(pay.get("freight"), dict):
                freight_amt = pay["freight"].get("amount")
            if freight_amt is not None:
                try:
                    freight = FreightQuote(amount=float(freight_amt), note=str(pay.get("freight_note") or "") or None)
                except (TypeError, ValueError):
                    freight = FreightQuote(amount=0, note="invalid freight")
            else:
                freight = FreightQuote(amount=0, note="供应商未返回运费（待供应侧被动物流）")
            grand = goods + float(freight.amount if freight else 0)
            return QuoteRow(
                partner=pref,
                status="ok",
                task_id=str(out.get("task_id") or pay.get("task_id") or "") or None,
                lead_time_days=pay.get("lead_time_days"),
                line_prices=[
                    {
                        "sku": quoted_sku or want_sku or line_sku,
                        "name": line_name,
                        "qty": qty,
                        "unit_price": unit,
                        "line_total": goods,
                        "supplier_agent_id": partner.get("agent_id"),
                    }
                ],
                goods_total=goods,
                freight=freight,
                grand_total=grand,
                raw_policy_hints=list(pay.get("policy_hints") or []),
            )

        async def _one_partner(partner: dict[str, Any]) -> list[QuoteRow]:
            return list(await asyncio.gather(*[_one_line(partner, ln) for ln in demand_lines]))

        nested = list(await asyncio.gather(*[_one_partner(p) for p in partners]))
        rows: list[QuoteRow] = [r for group in nested for r in group]
        ok_rows = [r for r in rows if r.status == "ok" and r.grand_total is not None]
        lowest = min(ok_rows, key=lambda r: float(r.grand_total or 0), default=None)

        # 覆盖面：每行物料哪些供应商报得出
        from agents.supplier_common.catalog_price import normalize_sku as _norm_sku

        coverage: dict[str, list[str]] = {}
        for ln in demand_lines:
            key = _norm_sku(str(ln.get("sku") or ln.get("name") or "")) or str(ln.get("name") or ln.get("sku"))
            coverage[key] = []
        for r in ok_rows:
            aid = (r.partner.agent_id if r.partner else None) or ""
            for lp in r.line_prices or []:
                sku = _norm_sku(str(lp.get("sku") or "")) or str(lp.get("sku") or "")
                if sku in coverage and aid and aid not in coverage[sku]:
                    coverage[sku].append(aid)
        # 拆单建议：多行且不同行最优供应商不同
        split_plan: list[dict[str, Any]] = []
        if multi:
            for sku, aids in coverage.items():
                if not aids:
                    continue
                # 该行取最低总价的供应商
                cands = [
                    r
                    for r in ok_rows
                    if (r.partner and r.partner.agent_id in aids)
                    and any(
                        (_norm_sku(str(lp.get("sku") or "")) or str(lp.get("sku") or "")) == sku
                        for lp in (r.line_prices or [])
                    )
                ]
                best = min(cands, key=lambda x: float(x.grand_total or 0), default=None)
                if best and best.partner and best.partner.agent_id:
                    split_plan.append(
                        {
                            "sku": sku,
                            "supplier_agent_id": best.partner.agent_id,
                            "grand_total": best.grand_total,
                            "unit_price": (best.line_prices[0] or {}).get("unit_price") if best.line_prices else None,
                        }
                    )

        # 写回 case quotes（兼容旧 compare；多行时每行一条）
        quote_envs = []
        for r in rows:
            if r.status != "ok" or not r.partner:
                continue
            lp0 = (r.line_prices or [{}])[0] or {}
            # 保留供应回执里的全量规格（重量/体积），供后续询运
            raw_pay = {}
            try:
                # QuoteRow 未直接存 raw；从 line_prices 扩展字段兜底
                raw_pay = {
                    "weight_kg": lp0.get("weight_kg"),
                    "volume_m3": lp0.get("volume_m3"),
                    "kg_per_unit": lp0.get("kg_per_unit"),
                    "pack_cm": lp0.get("pack_cm"),
                    "charge_class": lp0.get("charge_class"),
                }
            except Exception:  # noqa: BLE001
                raw_pay = {}
            # 若行上没有，按 SKU 主数据补齐
            if raw_pay.get("weight_kg") is None and lp0.get("sku"):
                try:
                    from commerce.seat_catalog import product_physical_specs

                    phys = product_physical_specs(str(lp0.get("sku")), qty=float(lp0.get("qty") or 1))
                    raw_pay.update(
                        {
                            "weight_kg": phys.get("weight_kg"),
                            "volume_m3": phys.get("volume_m3"),
                            "kg_per_unit": phys.get("kg_per_unit"),
                            "pack_cm": phys.get("pack_cm"),
                            "charge_class": phys.get("charge_class"),
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass
            quote_envs.append(
                {
                    "schema_type": "agentlink.initial_quote",
                    "payload": {
                        "supplier_agent_id": r.partner.agent_id,
                        "product_name": lp0.get("name") or lp0.get("sku"),
                        "sku": lp0.get("sku"),
                        "quantity": lp0.get("qty"),
                        "unit_price": lp0.get("unit_price"),
                        "lead_time_days": r.lead_time_days,
                        "freight_amount": r.freight.amount if r.freight else None,
                        "goods_total": r.goods_total,
                        "grand_total": r.grand_total,
                        "weight_kg": raw_pay.get("weight_kg"),
                        "volume_m3": raw_pay.get("volume_m3"),
                        "physical_specs": {k: v for k, v in raw_pay.items() if v is not None},
                        "product": {
                            "sku": lp0.get("sku"),
                            "name": lp0.get("name") or lp0.get("sku"),
                            "quantity": lp0.get("qty"),
                            "weight_kg": raw_pay.get("weight_kg"),
                            "volume_m3": raw_pay.get("volume_m3"),
                            "kg_per_unit": raw_pay.get("kg_per_unit"),
                            "pack_cm": raw_pay.get("pack_cm"),
                            "charge_class": raw_pay.get("charge_class"),
                        },
                    },
                }
            )
        comparison = compare_quotes(quote_envs) if quote_envs else None
        batch_dump = [r.model_dump() for r in rows]
        from commerce.auction_suitability import assess_group_auction_suitability

        # 组群竞价仅在单物料、多家可比时报；组合覆盖拆单优先
        suitability = assess_group_auction_suitability(
            case={**case, "shortlist": partners, "brief": brief},
            rfq_batch=batch_dump,
        )
        offer_auc = bool(suitability.get("offer")) and not multi
        distinct_suppliers = {str(x.get("supplier_agent_id")) for x in split_plan if x.get("supplier_agent_id")}
        suggest_split = multi and len(split_plan) >= 2 and len(distinct_suppliers) >= 2
        hitl_msg = (
            "组合询价已回；不同物料可由不同供应商覆盖，建议考虑分单采购"
            if suggest_split
            else (
                "已收到并行询价结果；请选择议价、组群竞价或选商"
                if offer_auc
                else "已收到并行询价结果；可议价或选商"
            )
        )
        pc.transition(
            cid,
            "COMPARE_PENDING",
            event="rfq_batch_done",
            patch={
                "quotes": quote_envs,
                "comparison": comparison,
                "rfq_batch": batch_dump,
                "line_coverage": coverage,
                "split_plan": split_plan,
                "auction_suitability": suitability,
                "hitl_pending": make_hitl(
                    "compare_decide",
                    hitl_msg,
                    options=["negotiate", "auction", "order"] if offer_auc else ["negotiate", "order"],
                ),
            },
        )
        self.memory.record(
            cid,
            event="rfq_batch_done",
            payload={"n": len(rows), "ok": len(ok_rows), "coverage": coverage, "split_plan": split_plan},
        )
        self.memory.inject(
            cid,
            [
                {
                    "key": "selected_shortlist",
                    "value": [p.get("candidate_id") or p.get("agent_id") for p in partners],
                    "tags": ["hitl", "shortlist"],
                },
                {"key": "latest_quotes", "value": batch_dump, "tags": ["quotes"]},
                {"key": "line_coverage", "value": coverage, "tags": ["quotes", "coverage"]},
            ],
        )
        supplier_ids = [
            str(p.get("agent_id") or "")
            for p in partners
            if p.get("agent_id")
        ]
        lowest_id = None
        if lowest and lowest.partner:
            lowest_id = lowest.partner.agent_id
        choices = post_quote_choices(
            case_id=cid,
            lowest_agent_id=lowest_id,
            supplier_ids=supplier_ids,
            offer_group_auction=offer_auc,
            auction_hint=str(suitability.get("hint") or "") or None,
            split_plan=split_plan if suggest_split else None,
            coverage=coverage if multi else None,
        )
        pc.update_case(cid, pending_choices=choices)
        out = RfqBatchOut(
            ok=len(ok_rows) > 0,
            case_id=cid,
            parallel=len(partners),
            quotes=rows,
            summary={
                "ok_count": len(ok_rows),
                "fail_count": len(rows) - len(ok_rows),
                "lowest_grand_total": lowest.grand_total if lowest else None,
                "lowest_partner_aic": lowest.partner.aic if lowest else None,
                "multi_line": multi,
                "coverage": coverage,
                "split_plan": split_plan,
                "suggest_split": suggest_split,
            },
            ui_hint={
                "view": "quote_compare_table",
                "table": self.calc_compare_table(cid).get("table"),
                "form": "choice_actions",
                "choices": choices.get("choices"),
                "allow_note": True,
                "title": choices.get("prompt"),
            },
            hitl={
                "gate": "after_initial_quotes",
                "options": [c.get("id") for c in (choices.get("choices") or [])],
            },
        )
        dumped = out.model_dump()
        dumped["presentation_hint"] = (
            "向用户汇报时必须用 Markdown 表格展示 quotes（列：供应商|物料|单价|货价合计|运费|总价|交期|状态）；"
            "若 summary.suggest_split=true，先说明「建议分单」并点选按钮；禁止散文枚举。"
        )
        dumped["choice_actions"] = choices
        dumped["auction_suitability"] = suitability
        dumped["line_coverage"] = coverage
        dumped["split_plan"] = split_plan
        return dumped

    async def partner_dialog(self, raw: dict[str, Any] | None = None) -> dict[str, Any]:
        inp = PartnerDialogIn.model_validate(raw or {})
        cid = self._resolve_case(inp.case_id)
        if not cid:
            return PartnerDialogOut(
                ok=False, case_id="", intent=inp.intent, error={"code": "NO_CASE", "message": "尚无采购案"}
            ).model_dump()
        case = pc.get_case(cid) or {}
        partner_raw = inp.partner
        if isinstance(partner_raw, str):
            partners = self._resolve_selected(case, [partner_raw])
            partner = partners[0] if partners else None
        else:
            partner = partner_raw
        if not partner:
            return PartnerDialogOut(
                ok=False, case_id=cid, intent=inp.intent, error={"code": "VALIDATION", "message": "未知 partner"}
            ).model_dump()
        pref = self._partner_from_candidate(partner)
        schema = "agentlink.bargain_round" if inp.intent in ("negotiate", "requote") else "agentlink.quote_request"
        brief = case.get("brief") or {}
        prev = next(
            (
                q
                for q in case.get("quotes") or []
                if (q.get("payload") or {}).get("supplier_agent_id") == partner.get("agent_id")
            ),
            None,
        )
        payload: dict[str, Any]
        dest = _rfq_destination()
        specs = _ensure_partner_specs(partner.get("agent_id"), brief.get("product_name"), brief.get("specifications"))
        if schema == "agentlink.bargain_round":
            prev_pay = (prev or {}).get("payload") if isinstance((prev or {}).get("payload"), dict) else {}
            prev_prod = prev_pay.get("product") if isinstance(prev_pay.get("product"), dict) else {}
            sku = (
                str(prev_prod.get("sku") or prev_pay.get("sku") or specs.get("sku") or "").strip()
                or None
            )
            if sku:
                specs = {**specs, "sku": sku}
            payload = {
                "round": len(case.get("negotiate_rounds") or []) + 1,
                "goal_text": inp.goal_text or inp.message or "优化总价",
                "previous_quote_id": prev_pay.get("quote_id"),
                "previous_unit_price": prev_pay.get("unit_price"),
                "product_name": prev_prod.get("name") or brief.get("product_name"),
                "sku": sku,
                "quantity": prev_prod.get("quantity") or brief.get("quantity"),
                "specifications": specs,
                "need_freight": False,
                "destination": dest,
                "postal_code": dest["postal_code"],
            }
        else:
            payload = {
                "purchase_request_id": brief.get("purchase_request_id"),
                "product_name": brief.get("product_name"),
                "quantity": brief.get("quantity"),
                "specifications": specs,
                "currency": "CNY",
                "clarify": inp.message or inp.goal_text,
                "need_freight": False,
                "destination": dest,
                "postal_code": dest["postal_code"],
            }
        envelope = wrap_business(schema, cid, payload)
        try:
            out = await aip_start_structured(
                partner_url=pref.endpoint,
                leader_aic=LEADER_AIC(),
                partner_aic=pref.aic,
                session_id=f"dialog-{inp.intent}-{cid}-{partner.get('agent_id')}",
                envelope=envelope,
                local_agent_id=_buyer_agent_id(),
            )
        except Exception as exc:  # noqa: BLE001
            return PartnerDialogOut(
                ok=False,
                case_id=cid,
                partner=pref,
                intent=inp.intent,
                error={"code": "AIP_ERROR", "message": str(exc)},
            ).model_dump()
        state = str(out.get("state") or "").lower()
        env = out.get("envelope") or {}
        pay = env.get("payload") if isinstance(env, dict) else {}
        if not isinstance(pay, dict):
            pay = {}
        reject_msg = str(out.get("message") or "").strip()
        if state in {"rejected", "failed"}:
            return PartnerDialogOut(
                ok=False,
                case_id=cid,
                partner=pref,
                intent=inp.intent,
                error={"code": "REJECTED", "message": reject_msg or "供应侧拒绝"},
            ).model_dump()
        if state in {"awaiting-input", "input-required"} and not pay.get("unit_price"):
            return PartnerDialogOut(
                ok=False,
                case_id=cid,
                partner=pref,
                intent=inp.intent,
                error={"code": "AWAITING_INPUT", "message": reject_msg or "供应侧要求补充规格后才能报价"},
            ).model_dump()
        unit = pay.get("unit_price")
        qty = float(
            (pay.get("product") or {}).get("quantity")
            if isinstance(pay.get("product"), dict) and (pay.get("product") or {}).get("quantity") is not None
            else brief.get("quantity")
            or 1
        )
        goods = pay.get("goods_total")
        if goods is None and unit is not None:
            goods = float(unit) * qty
        goods_after = pay.get("goods_after_promo")
        freight_amt = pay.get("freight_amount")
        if freight_amt is None and isinstance(pay.get("freight"), dict):
            freight_amt = pay["freight"].get("amount")
        freight = (
            {"amount": float(freight_amt), "currency": "CNY"}
            if freight_amt is not None
            else {"amount": 0, "note": "未返回运费"}
        )
        base_goods = float(goods_after if goods_after is not None else goods or 0)
        grand = base_goods + float(freight.get("amount") or 0) if goods is not None or goods_after is not None else None
        policy = pay.get("policy")
        if not isinstance(policy, dict) or not policy:
            # 兼容旧回执：从议价字段拼可读政策
            if pay.get("policy_hints") or pay.get("talk_track") or pay.get("promotions_disclosed"):
                policy = {
                    "disclosed": bool(pay.get("promotions_disclosed", True)),
                    "hints": list(pay.get("policy_hints") or []),
                    "talk_track": pay.get("talk_track"),
                    "next_tier": (pay.get("promo_settlement") or {}).get("next_tier")
                    if isinstance(pay.get("promo_settlement"), dict)
                    else None,
                    "reach_example": None,
                }
            else:
                policy = None
        result = {
            "status": out.get("state"),
            "unit_price": unit,
            "quantity": qty,
            "goods_total": goods,
            "goods_after_promo": goods_after,
            "freight": freight,
            "grand_total": grand,
            "line_prices": [
                {
                    "sku": (pay.get("product") or {}).get("sku")
                    if isinstance(pay.get("product"), dict)
                    else brief.get("product_name"),
                    "name": (pay.get("product") or {}).get("name")
                    if isinstance(pay.get("product"), dict)
                    else brief.get("product_name"),
                    "qty": qty,
                    "unit_price": unit,
                    "line_total": goods,
                }
            ],
            "product": pay.get("product"),
            "volume_m3": pay.get("volume_m3"),
            "weight_kg": pay.get("weight_kg"),
            "policy": policy,
            "policy_hints": list(pay.get("policy_hints") or (policy or {}).get("hints") or []),
            "talk_track": pay.get("talk_track") or (policy or {}).get("talk_track"),
            "counter_options": pay.get("counter_options") or [],
            "reach_promo_preview": pay.get("reach_promo_preview"),
            "promotions_disclosed": bool(
                pay.get("promotions_disclosed")
                if pay.get("promotions_disclosed") is not None
                else bool(policy)
            ),
            "note": pay.get("note") or inp.message,
        }
        self.memory.record(
            cid,
            event=f"dialog_{inp.intent}",
            payload={"partner": pref.aic, "grand_total": grand},
            ref_ids=[str(out.get("task_id") or "")],
        )
        # 人类话术改量（如「改为500」）写回案，供后续 decide_order 使用
        import re

        decided_qty = None
        blob = f"{inp.message or ''} {inp.goal_text or ''}"
        m = re.search(r"(?:改为|改成|改买|购买|下单|要)\s*(\d{2,6})\s*(?:套|件|只|个)?", blob)
        if not m:
            m = re.search(r"(\d{2,6})\s*(?:套|件|只|个).*(?:下单|购买|优惠后)", blob)
        if m:
            try:
                decided_qty = int(m.group(1))
            except (TypeError, ValueError):
                decided_qty = None
        if decided_qty and decided_qty > 0:
            result["ordered_quantity"] = decided_qty
            try:
                brief = dict((pc.get_case(cid) or {}).get("brief") or {})
                brief["decided_quantity"] = decided_qty
                brief["quantity"] = decided_qty
                pc.update_case(cid, brief=brief)
            except Exception:  # noqa: BLE001
                pass
        if inp.intent in ("negotiate", "requote"):
            try:
                case_now = pc.get_case(cid) or {}
                rounds = list(case_now.get("negotiate_rounds") or [])
                rounds.append(
                    {
                        "intent": inp.intent,
                        "partner": partner.get("agent_id") if isinstance(partner, dict) else partner,
                        "goal_text": inp.goal_text or inp.message,
                        "result": result,
                    }
                )
                pc.update_case(cid, negotiate_rounds=rounds[-12:])
                # 议价后进入可下单回顾
                if case_now.get("state") in ("COMPARE_PENDING", "SOURCING", "NEGOTIATING"):
                    pc.transition(cid, "NEGOTIATE_REVIEW", event="dialog_negotiate")
            except Exception:  # noqa: BLE001
                pass
        dumped = PartnerDialogOut(
            ok=bool(env),
            case_id=cid,
            partner=pref,
            intent=inp.intent,
            task_id=str(out.get("task_id") or "") or None,
            result=result,
        ).model_dump()
        if inp.intent in ("negotiate", "requote"):
            dumped["presentation_hint"] = (
                "议价回执必须用表格展示：供应商|物料|数量|挂牌单价|货价|活动说明|凑门槛对照；"
                "活动说明取自 result.policy / policy_hints / talk_track；"
                "若有 reach_example 或 counter_options，写出「例如买满 N 件，目录总价 x，优惠后 y」；"
                "人类若已改量，下单时 flow.decide_order 必须传 quantity=最终数量；"
                "规格取自 product/volume_m3/weight_kg，禁止无依据说「没有收到规格参数」。"
            )
        elif inp.intent in ("initial_quote", "quote", ""):
            dumped["presentation_hint"] = (
                "初询只展示挂牌价与产品规格（体积/重量/包装）；不要主动谈优惠活动；"
                "有 product/volume_m3/weight_kg 就必须转述，禁止说未收到规格。"
            )
        return dumped

    def calc_compare_table(self, case_id: str | None = None) -> dict[str, Any]:
        cid = self._resolve_case(case_id)
        if not cid:
            return {"ok": False, "error": {"code": "NO_CASE", "message": "尚无采购案"}}
        case = pc.get_case(cid) or {}
        rows = case.get("rfq_batch") or []
        if not rows:
            # 从 quotes 凑
            for q in case.get("quotes") or []:
                pay = q.get("payload") or {}
                rows.append(
                    {
                        "partner": {"agent_id": pay.get("supplier_agent_id"), "name": pay.get("supplier_agent_id")},
                        "goods_total": pay.get("goods_total"),
                        "freight": {"amount": pay.get("freight_amount") or 0},
                        "grand_total": pay.get("grand_total"),
                        "lead_time_days": pay.get("lead_time_days"),
                        "status": "ok",
                    }
                )
        table = {
            "headers": ["供应商", "状态", "货价", "运费", "总价", "交期(天)"],
            "rows": [],
        }
        for r in rows:
            p = r.get("partner") or {}
            fr = r.get("freight") or {}
            table["rows"].append(
                [
                    p.get("name") or p.get("agent_id") or p.get("aic") or "?",
                    r.get("status"),
                    r.get("goods_total"),
                    fr.get("amount") if isinstance(fr, dict) else fr,
                    r.get("grand_total"),
                    r.get("lead_time_days"),
                ]
            )
        supplier_ids = []
        lowest_id = None
        best = None
        for r in rows:
            p = r.get("partner") or {}
            sid = p.get("agent_id")
            if sid:
                supplier_ids.append(str(sid))
            gt = r.get("grand_total")
            if gt is not None and r.get("status") == "ok":
                try:
                    gtf = float(gt)
                except (TypeError, ValueError):
                    continue
                if best is None or gtf < best:
                    best = gtf
                    lowest_id = str(sid) if sid else lowest_id
        from commerce.auction_suitability import assess_group_auction_suitability

        suitability = assess_group_auction_suitability(case=case)
        split_plan = case.get("split_plan") if isinstance(case.get("split_plan"), list) else None
        coverage = case.get("line_coverage") if isinstance(case.get("line_coverage"), dict) else None
        multi = bool((case.get("brief") or {}).get("combo") or len((case.get("brief") or {}).get("lines") or []) >= 2)
        offer_auc = bool(suitability.get("offer")) and not multi
        choices = post_quote_choices(
            case_id=cid,
            lowest_agent_id=lowest_id,
            supplier_ids=supplier_ids,
            offer_group_auction=offer_auc,
            auction_hint=str(suitability.get("hint") or "") or None,
            split_plan=split_plan,
            coverage=coverage,
        )
        pc.update_case(cid, pending_choices=choices, auction_suitability=suitability)
        return {
            "ok": True,
            "case_id": cid,
            "table": table,
            "choice_actions": choices,
            "auction_suitability": suitability,
            "ui_hint": {
                "view": "quote_compare_table",
                "table": table,
                "form": "choice_actions",
                "choices": choices.get("choices"),
                "allow_note": True,
                "title": choices.get("prompt"),
            },
            "hitl": choices.get("hitl"),
            "presentation_hint": (
                "向用户汇报比价时必须用 Markdown 表格（列对齐 table.headers），表前一句结论；禁止散文枚举。"
            ),
        }

    # —— 本地业务薄封装 ——
    def query_inventory(self, low_only: bool = False) -> dict[str, Any]:
        items = bs.list_inventory()
        if low_only:
            items = [i for i in items if i.get("low")]
        return {
            "ok": True,
            "items": items,
            "low_count": sum(1 for i in items if i.get("low")),
            "presentation_hint": "用 Markdown 表格展示库存（编码|名称|可用|安全库存|单位|状态）。",
        }

    def query_orders(self, kind: str = "sales", limit: int = 20) -> dict[str, Any]:
        if kind == "purchase":
            cases = pc.list_cases(limit)
            return {
                "ok": True,
                "kind": kind,
                "items": [
                    {
                        "case_id": c.get("case_id"),
                        "state": c.get("state"),
                        "product": (c.get("brief") or {}).get("product_name"),
                        "qty": (c.get("brief") or {}).get("quantity"),
                        "selected": c.get("selected_supplier"),
                    }
                    for c in cases
                ],
            }
        return {"ok": True, "kind": "sales", "items": bs.list_sales_orders(limit)}

    def query_notifications(self, unread_only: bool = False, limit: int = 20) -> dict[str, Any]:
        items = bs.list_notifications(unread_only=unread_only, limit=limit)
        return {"ok": True, "items": items, "unread": sum(1 for n in items if not n.get("read"))}


# 进程内单例，供 Wit 与路由共用
_SERVICE: BuyerToolService | None = None


def get_buyer_tools() -> BuyerToolService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = BuyerToolService()
    return _SERVICE
