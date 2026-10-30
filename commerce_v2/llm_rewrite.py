# -*- coding: utf-8 -*-
"""需求改写：先检索画像/库存/供应目录，再 LLM 消歧绑定（无硬规则默认脚轮）。"""
from __future__ import annotations

import json
import re
from typing import Any

from commerce_v2.catalog import SUPPLIERS
from commerce_v2.demand_items import enrich_brief_items
from commerce_v2.rewrite_grounding import format_evidence_for_prompt, gather_rewrite_evidence

_SYSTEM = """你是工业采购需求消歧与改写器。

你必须先阅读「检索依据」（采购画像、本厂库存物料、供应目录库存），再决定用户原话指代哪条物料。

硬性约束：
1. 改写依据只能来自检索依据 + 用户原话；禁止臆造目录外 SKU。
2. 用户点名品类（如坐垫/面料/脚轮）时，必须在本厂物料或供应目录中做名称/别名匹配；禁止改写成无关品类（尤其禁止把坐垫/面料改成脚轮）。
3. 用户同时点名多个品类（如「500脚轮和400坐垫」）时必须全部保留在 rewritten_query 与 items 中，禁止丢掉任一品类。
4. 绑定优先级：本厂物料表（含 preferred_supplier） > 供应目录同名/近义 SKU > 无法匹配则 sku="" 仍保留用户品类。
5. 采购画像只用于在「多名候选」时消歧（例如高端线偏好记忆海绵/高档面料），不得覆盖用户已点名的品类。
6. hint 必须写清依据：引用了哪条库存/目录/画像字段。
7. 只输出一个 JSON 对象。

输出字段：
{
  "rewritten_query": "采购…（完整中文需求句，含全部品类的数量单位与物料名）",
  "name": "主物料中文名（多品时取第一项）",
  "qty": 数字,
  "unit": "套|米|件|只|个|块|对|根",
  "sku": "目录或本厂物料编码，无法匹配则空串",
  "preferred_supplier": "偏好供应 agent_id 或空串",
  "items": [{"name":"…","qty":数字,"unit":"…","sku":"…"}],
  "hint": "改写依据（须引用检索字段）",
  "evidence_used": ["短证据条目1", "短证据条目2"]
}
"""


def _catalog_sku_set() -> set[str]:
    out: set[str] = set()
    for meta in SUPPLIERS.values():
        out.update((meta.get("skus") or {}).keys())
    return out


def _safe_fallback(text: str, agent_id: str, *, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = (text or "").strip() or "采购需求"
    qty = 1
    m = re.search(r"(\d+)", raw)
    if m:
        qty = int(m.group(1))
    # 尝试用库存名称做最简子串匹配（非硬规则默认脚轮）
    sku, name, unit, pref = "", raw, "件", ""
    for it in (evidence or {}).get("buyer_inventory") or []:
        n = str(it.get("name") or "")
        if n and any(tok in raw for tok in (n, n.replace("座椅", ""), n[-2:])):
            if any(k in raw for k in ("坐垫", "海绵", "面料", "脚轮", "扶手")) or n[:2] in raw:
                sku = str(it.get("code") or "")
                name = n
                unit = str(it.get("unit") or "件")
                pref = str(it.get("preferred_supplier") or "")
                break
    if "米" in raw:
        unit = "米"
    elif "套" in raw and not unit:
        unit = "套"
    out = {
        "sku": sku,
        "name": name[:40] if not sku else name,
        "qty": qty,
        "unit": unit,
        "preferred_supplier": pref,
        "rewritten_query": raw if raw.startswith("采购") else f"采购{raw}",
        "raw": text or "",
        "hint": "LLM暂不可用：已用库存名称子串尝试绑定，未默认脚轮",
        "evidence_used": [],
        "rewrite_engine": "fallback_grounded",
        "grounding": evidence or {},
    }
    return enrich_brief_items(out, text=raw, evidence=evidence)


def _parse_json_obj(content: str) -> dict[str, Any] | None:
    s = (content or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None


async def rewrite_demand_llm(text: str, agent_id: str) -> dict[str, Any]:
    from commerce.env_loader import llm_enabled, llm_settings, load_dotenv

    load_dotenv()
    evidence = gather_rewrite_evidence(agent_id)
    if not llm_enabled():
        return _safe_fallback(text, agent_id, evidence=evidence)

    known = _catalog_sku_set()
    for it in evidence.get("buyer_inventory") or []:
        if it.get("code"):
            known.add(str(it["code"]))

    user = (
        "【检索依据——必须先读再改写】\n"
        f"{format_evidence_for_prompt(evidence)}\n\n"
        f"【用户原话】{(text or '').strip()}\n"
        f"【采购方】{agent_id}"
    )
    cfg = llm_settings()
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"] or None)
        resp = await client.chat.completions.create(
            model=cfg["model"] or "deepseek-chat",
            temperature=0.1,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        content = (resp.choices[0].message.content or "").strip()
        obj = _parse_json_obj(content)
        if not obj:
            return _safe_fallback(text, agent_id, evidence=evidence)
    except Exception as exc:  # noqa: BLE001
        out = _safe_fallback(text, agent_id, evidence=evidence)
        out["hint"] = f"LLM改写失败已回退检索绑定：{str(exc)[:120]}"
        out["rewrite_engine"] = "fallback_error"
        return out

    sku = str(obj.get("sku") or "").strip()
    if sku and sku not in known:
        sku = ""
    qty = obj.get("qty")
    try:
        qty = int(float(qty))
    except (TypeError, ValueError):
        m = re.search(r"(\d+)", text or "")
        qty = int(m.group(1)) if m else 1
    name = str(obj.get("name") or "").strip() or "未指明物料"
    unit = str(obj.get("unit") or "件").strip() or "件"
    q = str(obj.get("rewritten_query") or "").strip() or f"采购{qty}{unit}{name}"
    pref = str(obj.get("preferred_supplier") or "").strip()
    raw = text or ""
    user_wants_caster = any(k in raw for k in ("脚轮", "轮子", "caster"))
    # 防幻觉：仅当用户未提脚轮、却改写成脚轮时拦截（多品同时点名脚轮+坐垫必须保留）
    non_caster = any(k in raw for k in ("坐垫", "面料", "海绵", "软垫", "织物", "布料", "扶手", "椅背"))
    if non_caster and not user_wants_caster and ("脚轮" in q or sku.startswith("RM-CASTER")):
        rebound = _safe_fallback(text, agent_id, evidence=evidence)
        rebound["hint"] = "已拦截脚轮幻觉；按库存/目录重新绑定"
        rebound["rewrite_engine"] = "llm_guard_rebind"
        return rebound

    used = obj.get("evidence_used") or []
    if not isinstance(used, list):
        used = [str(used)]
    llm_items = obj.get("items") if isinstance(obj.get("items"), list) else []
    out = {
        "sku": sku,
        "name": name,
        "qty": qty,
        "unit": unit,
        "preferred_supplier": pref,
        "rewritten_query": q,
        "raw": raw,
        "hint": str(obj.get("hint") or "基于画像与库存/目录的 LLM 消歧").strip(),
        "evidence_used": [str(x) for x in used][:6],
        "rewrite_engine": "llm_grounded",
        "items": [
            {
                "sku": str(it.get("sku") or ""),
                "name": str(it.get("name") or ""),
                "qty": it.get("qty") or 1,
                "unit": str(it.get("unit") or "件"),
            }
            for it in llm_items
            if isinstance(it, dict)
        ],
        "grounding": {
            "buyer_profile": evidence.get("buyer_profile"),
            "inventory_hits": [
                x
                for x in (evidence.get("buyer_inventory") or [])
                if not sku or x.get("code") == sku or (name and name in str(x.get("name") or ""))
            ][:5],
            "catalog_hits": [
                x
                for x in (evidence.get("supplier_catalog") or [])
                if not sku or x.get("sku") == sku or (name and name in str(x.get("name") or ""))
            ][:8],
        },
    }
    return enrich_brief_items(out, text=raw, evidence=evidence)
