# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Any

from commerce_v2.catalog import SUPPLIERS, local_candidates_for_sku, _rpc


def _owners_for_skus(skus: list[str]) -> set[str]:
    owners: set[str] = set()
    for sku in skus:
        s = (sku or "").strip()
        if not s:
            continue
        for aid, meta in SUPPLIERS.items():
            catalog = meta.get("skus") or {}
            if s in catalog:
                owners.add(aid)
                continue
            # 前缀：RM-FOAM / RM-CASTER
            prefix = "-".join(s.split("-")[:2]) if s.startswith("RM-") else s
            if any(k.startswith(prefix) for k in catalog):
                owners.add(aid)
    return owners


def _rank_by_sku(cands: list[dict[str, Any]], sku: str) -> list[dict[str, Any]]:
    """有目录 SKU 时按供应能力过滤；无 SKU（LLM 未映射）则保留平台原序。"""
    return _rank_by_skus(cands, [sku] if sku else [])


def _rank_by_skus(cands: list[dict[str, Any]], skus: list[str]) -> list[dict[str, Any]]:
    cleaned = [str(s).strip() for s in skus if str(s or "").strip()]
    if not cleaned:
        return cands[:8]
    owners = _owners_for_skus(cleaned)
    if not owners:
        return cands[:8]
    preferred = [c for c in cands if str(c.get("agent_id") or "") in owners]
    others = [c for c in cands if str(c.get("agent_id") or "") not in owners]
    if preferred:
        return preferred[:8]
    return (others or cands)[:8]


async def discover_suppliers(query: str, *, sku: str, agent_id: str = "buyer-a") -> dict[str, Any]:
    """真实梧桐 ADP；仅当平台无结果或显式 local 时才用本地黄页，并标明 degrade。"""
    mode = (os.getenv("V2_DISCOVERY_MODE") or "auto").lower()
    adp_error: str | None = None
    adp_meta: dict[str, Any] = {}

    if mode != "local":
        try:
            from commerce.discovery import discover_suppliers as adp_discover

            # 注意：底层参数是 bypass_cache，不是 refresh（旧错误关键字会导致整段 ADP 被 except 吃掉）
            raw = await adp_discover(query, limit=8, bypass_cache=True)
            adp_meta = {
                "platform_error": raw.get("platform_error"),
                "discovery_url": raw.get("discovery_url") or raw.get("used_url"),
                "source_raw": raw.get("source"),
            }
            cands = raw.get("candidates") or raw.get("items") or []
            if cands:
                norm = []
                for c in cands:
                    aid = c.get("agent_id") or c.get("id")
                    if not aid or str(aid) == "unknown":
                        continue
                    norm.append(
                        {
                            "agent_id": aid,
                            "candidate_id": aid,
                            "title": c.get("title") or c.get("name") or aid,
                            "city": c.get("city") or "",
                            "blurb": c.get("description") or c.get("blurb") or "",
                            "endpoint": c.get("endpoint") or c.get("url") or _rpc(str(aid)),
                            "source": "platform_adp",
                        }
                    )
                norm = _rank_by_sku(norm, sku)
                if norm:
                    return {
                        "source": "platform_adp",
                        "candidates": norm,
                        "degrade": False,
                        "meta": adp_meta,
                    }
            adp_error = str(raw.get("platform_error") or "platform_adp_empty")
        except TypeError as e:
            # 兼容误传 refresh 等
            adp_error = f"adp_call_type_error:{e}"
        except Exception as e:  # noqa: BLE001
            adp_error = str(e)[:240]
            if mode == "adp_only":
                return {
                    "source": "adp_error",
                    "candidates": [],
                    "error": adp_error,
                    "degrade": True,
                    "meta": adp_meta,
                }

    if mode == "adp_only":
        return {
            "source": "adp_error",
            "candidates": [],
            "error": adp_error or "no_candidates",
            "degrade": True,
            "meta": adp_meta,
        }

    local = _rank_by_sku(local_candidates_for_sku(sku), sku)
    return {
        "source": "local_directory",
        "candidates": local,
        "degrade": True,
        "error": adp_error,
        "note": "ADP未命中或未配置，已降级本地黄页（按 SKU 过滤）",
        "meta": adp_meta,
    }


def _skus_from_brief(brief: dict[str, Any] | None) -> list[str]:
    brief = brief or {}
    skus: list[str] = []
    for it in brief.get("items") or []:
        if isinstance(it, dict) and it.get("sku"):
            skus.append(str(it["sku"]))
    if brief.get("sku"):
        skus.append(str(brief["sku"]))
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for s in skus:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


async def discover_suppliers_for_brief(
    query: str, *, brief: dict[str, Any], agent_id: str = "buyer-a"
) -> dict[str, Any]:
    """按 brief.items 全部 SKU 并集发现，避免多品只命中一家品类。"""
    skus = _skus_from_brief(brief)
    if len(skus) <= 1:
        return await discover_suppliers(query, sku=(skus[0] if skus else str(brief.get("sku") or "")), agent_id=agent_id)

    merged: dict[str, dict[str, Any]] = {}
    metas: list[dict[str, Any]] = []
    sources: list[str] = []
    degrade = False
    last_error: str | None = None
    for sku in skus:
        disc = await discover_suppliers(query, sku=sku, agent_id=agent_id)
        sources.append(str(disc.get("source") or ""))
        if disc.get("degrade"):
            degrade = True
        if disc.get("error"):
            last_error = str(disc.get("error"))
        metas.append({"sku": sku, "source": disc.get("source"), "n": len(disc.get("candidates") or [])})
        for c in disc.get("candidates") or []:
            aid = str(c.get("agent_id") or "")
            if aid and aid not in merged:
                merged[aid] = c

    # 本地再并一次，保证目录有货的供应不漏
    for sku in skus:
        for c in local_candidates_for_sku(sku):
            aid = str(c.get("agent_id") or "")
            if aid and aid not in merged:
                merged[aid] = {**c, "source": c.get("source") or "local_directory"}

    ranked = _rank_by_skus(list(merged.values()), skus)
    src = "platform_adp" if any(s == "platform_adp" for s in sources) and not degrade else (
        sources[0] if sources else "local_directory"
    )
    if any(s == "platform_adp" for s in sources) and any(s == "local_directory" for s in sources):
        src = "mixed_multi_sku"
    return {
        "source": src,
        "candidates": ranked,
        "degrade": degrade,
        "error": last_error,
        "note": f"多品发现并集 skus={skus}",
        "meta": {"per_sku": metas, "skus": skus},
    }

async def aip_call(
    partner_url: str,
    partner_aic: str,
    envelope: dict[str, Any],
    *,
    leader_aic: str,
    session_id: str | None = None,
    local_agent_id: str | None = None,
) -> dict[str, Any]:
    from uuid import uuid4

    from agentlink_runtime.aip_client_util import aip_start_structured

    sid = session_id or f"v2-{envelope.get('business_id') or 'biz'}-{uuid4().hex[:8]}"
    return await aip_start_structured(
        partner_url=partner_url,
        partner_aic=partner_aic,
        leader_aic=leader_aic,
        session_id=sid,
        envelope=envelope,
        local_agent_id=local_agent_id,
    )


def extract_business(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        # aip_start_structured 标准回执
        env = result.get("envelope")
        if isinstance(env, dict) and env:
            # Partner pipeline 可能再包一层 quote/scheme
            if env.get("quote") or env.get("scheme") or env.get("bid") or env.get("ok") is not None:
                return env
            if env.get("schema_type"):
                return env
            payload = env.get("payload")
            if isinstance(payload, dict):
                return payload
        if "business" in result and isinstance(result["business"], dict):
            return result["business"]
        data = result.get("data") or result.get("payload")
        if isinstance(data, dict) and ("schema_type" in data or "quote" in data or "scheme" in data):
            return data
        items = result.get("dataItems") or result.get("data_items") or []
        for it in items:
            if isinstance(it, dict) and it.get("structured"):
                return it["structured"]
            if isinstance(it, dict) and it.get("schema_type"):
                return it
        if result.get("schema_type") or result.get("quote") or result.get("ok") is not None:
            return result
    return {}
