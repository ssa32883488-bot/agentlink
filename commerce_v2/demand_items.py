# -*- coding: utf-8 -*-
"""多品需求拆行：从用户原话提取脚轮/坐垫/面料等并行行项目。"""
from __future__ import annotations

import re
from typing import Any

from commerce_v2.catalog import SUPPLIERS

_CATEGORY_SPECS: list[dict[str, Any]] = [
    {
        "keys": ("脚轮", "轮子", "caster"),
        "prefix": "RM-CASTER",
        "label": "脚轮",
        "unit": "只",
        "default_sku": "RM-CASTER-300",
    },
    {
        "keys": ("坐垫", "海绵", "记忆棉", "foam"),
        "prefix": "RM-FOAM",
        "label": "坐垫",
        "unit": "块",
        "default_sku": "RM-FOAM-MEM",
    },
    {
        "keys": ("面料", "织物", "fabric"),
        "prefix": "RM-FABRIC",
        "label": "面料",
        "unit": "套",
        "default_sku": "RM-FABRIC-PRO",
    },
]


def _qty_near(text: str, word: str, default: int) -> int:
    m = re.search(rf"(\d+)\s*{word}", text or "")
    if m:
        return int(m.group(1))
    m2 = re.search(rf"{word}\s*(\d+)", text or "")
    return int(m2.group(1)) if m2 else default


def _keys_for_prefix(prefix: str) -> tuple[str, ...]:
    for spec in _CATEGORY_SPECS:
        if spec["prefix"] == prefix:
            return tuple(spec["keys"])
    return ()


def _bind_from_evidence(prefix: str, label: str, unit: str, default_sku: str, evidence: dict[str, Any] | None) -> tuple[str, str, str, str]:
    ev = evidence or {}
    keys = _keys_for_prefix(prefix)
    for it in ev.get("buyer_inventory") or []:
        code = str(it.get("code") or "")
        name = str(it.get("name") or "")
        hit = code.startswith(prefix) or any(k in name for k in keys) or (label and label in name)
        if hit:
            return (
                code or default_sku,
                name or label,
                str(it.get("unit") or unit),
                str(it.get("preferred_supplier") or ""),
            )
    for row in ev.get("supplier_catalog") or []:
        sku = str(row.get("sku") or "")
        if sku.startswith(prefix):
            return sku, str(row.get("name") or label), str(row.get("unit") or unit), ""
    for meta in SUPPLIERS.values():
        for sku, item in (meta.get("skus") or {}).items():
            if sku.startswith(prefix):
                return sku, str(item.get("name") or label), str((item.get("spec") or {}).get("unit") or unit), ""
    return default_sku, label, unit, ""

def extract_line_items(text: str, evidence: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """从原话抽多品行；单品也返回 0~1 行（无关键词则空）。"""
    raw = text or ""
    lines: list[dict[str, Any]] = []
    for spec in _CATEGORY_SPECS:
        if not any(k in raw for k in spec["keys"]):
            continue
        # 数量：优先「500脚轮」；否则取全文第一个数字作弱默认
        qty = _qty_near(raw, spec["keys"][0], 0)
        if not qty:
            for k in spec["keys"][1:]:
                qty = _qty_near(raw, k, 0)
                if qty:
                    break
        if not qty:
            m = re.search(r"(\d+)", raw)
            qty = int(m.group(1)) if m else 1
        sku, name, unit, pref = _bind_from_evidence(
            spec["prefix"], spec["label"], spec["unit"], spec["default_sku"], evidence
        )
        # 坐垫偏好记忆海绵命名
        if spec["prefix"] == "RM-FOAM" and ("记忆" in raw or "海绵" in raw):
            for meta in SUPPLIERS.values():
                if "RM-FOAM-MEM" in (meta.get("skus") or {}):
                    sku = "RM-FOAM-MEM"
                    name = str(meta["skus"]["RM-FOAM-MEM"].get("name") or name)
                    break
        lines.append(
            {
                "sku": sku,
                "name": name,
                "qty": qty,
                "unit": unit,
                "preferred_supplier": pref,
                "prefix": spec["prefix"],
            }
        )
    return lines


def format_items_query(items: list[dict[str, Any]]) -> str:
    parts = []
    for it in items:
        parts.append(f"{it.get('qty')}{it.get('unit') or ''}{it.get('name') or it.get('sku')}")
    return "采购" + "和".join(parts) if parts else ""


def enrich_brief_items(brief: dict[str, Any], *, text: str | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """把多品行写回 brief；保留兼容字段 sku/name/qty = 首行。"""
    raw = text or brief.get("raw") or brief.get("rewritten_query") or ""
    items = extract_line_items(raw, evidence)
    if not items:
        if brief.get("sku") or brief.get("name"):
            brief.setdefault(
                "items",
                [
                    {
                        "sku": brief.get("sku") or "",
                        "name": brief.get("name") or "",
                        "qty": brief.get("qty") or 1,
                        "unit": brief.get("unit") or "件",
                    }
                ],
            )
        return brief
    brief["items"] = items
    brief["multi"] = len(items) >= 2
    # 兼容：主字段取首行（发现阶段还会用 items 并集）
    first = items[0]
    if len(items) >= 2 or not brief.get("sku"):
        brief["sku"] = first.get("sku") or brief.get("sku") or ""
        brief["name"] = first.get("name") or brief.get("name") or ""
        brief["qty"] = first.get("qty") or brief.get("qty") or 1
        brief["unit"] = first.get("unit") or brief.get("unit") or "件"
    q = format_items_query(items)
    if q and (len(items) >= 2 or "和" not in str(brief.get("rewritten_query") or "")):
        brief["rewritten_query"] = q
    brief.setdefault("raw", raw)
    return brief


def resolve_supplier_sku(supplier_id: str, line: dict[str, Any]) -> str | None:
    """供应目录上解析可报的 SKU；无能力返回 None。"""
    skus = (SUPPLIERS.get(supplier_id) or {}).get("skus") or {}
    if not skus:
        return None
    want = str(line.get("sku") or "")
    if want in skus:
        return want
    prefix = str(line.get("prefix") or "")
    if not prefix:
        for spec in _CATEGORY_SPECS:
            if want.startswith(spec["prefix"]) or any(k in str(line.get("name") or "") for k in spec["keys"]):
                prefix = spec["prefix"]
                break
    if not prefix:
        return None
    cands = [k for k in skus if k.startswith(prefix)]
    if not cands:
        return None
    for hint in ("MEM", "300", "PRO"):
        for k in cands:
            if hint in k:
                return k
    return sorted(cands)[0]


def bid_matches_line(bid: dict[str, Any], line: dict[str, Any]) -> bool:
    bsku = str(bid.get("sku") or "")
    lsku = str(line.get("sku") or "")
    if bsku and lsku and (bsku == lsku or bsku.split("-")[:2] == lsku.split("-")[:2]):
        return True
    prefix = str(line.get("prefix") or "")
    if prefix and bsku.startswith(prefix):
        return True
    name = str(line.get("name") or "")
    bname = str(bid.get("name") or "")
    if name and name[:2] in bname:
        return True
    return False
