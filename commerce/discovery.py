"""ADP 发现：仅梧桐平台；未命中即无候选（不做本地 ACS 兜底）。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

try:
    from commerce.progress import report
except ImportError:  # 供应侧精简部署时可能无 progress 模块

    def report(text: str, *, phase: str = "") -> None:  # type: ignore[misc]
        return None

_ROOT = Path(__file__).resolve().parents[1]
_ACS_DIR = _ROOT / "acs"

# 编排层短 TTL 缓存（不改协议；演示二次发现提速）
_DISCOVER_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SEC = float(os.getenv("ADP_DISCOVER_CACHE_TTL", "60") or "60")

# 演示用固定供应商 ACS（本地黄页兜底）
_LOCAL_SUPPLIER_ACS = (
    "supplier-agent-a.acs.json",
    "supplier-agent-b.acs.json",
    "supplier-agent-c.acs.json",
)


# 平台 ADP 可能仍登记旧 AIC；运行时以证书 CN（env）为准。新旧标记均识别。
_SUPPLIER_AIC_MARKERS = {
    "supplier-a": ("WP4OOG", "NH4J42"),
    "supplier-b": ("6CW2XR", "SHDUXP"),
    "supplier-c": ("1VQMIO", "8R39K3"),
}
_LOGISTICS_AIC_MARKERS = ("JOBNF9", "ZBD999")


def _aic_matches(aic: str, markers: tuple[str, ...]) -> bool:
    return any(m in aic for m in markers)


def _bind_live_peer(c: dict[str, Any]) -> None:
    """平台返回的 AIC 可能过期；用本域 env（证书 CN）覆盖 aic/endpoint。"""
    aid = str(c.get("agent_id") or "")
    if aid == "supplier-a":
        env_k, url_k = "SUPPLIER_A_AIC", "SUPPLIER_A_RPC_URL"
    elif aid == "supplier-b":
        env_k, url_k = "SUPPLIER_B_AIC", "SUPPLIER_B_RPC_URL"
    elif aid == "supplier-c":
        env_k, url_k = "SUPPLIER_C_AIC", "SUPPLIER_C_RPC_URL"
    elif aid == "logistics":
        env_k, url_k = "LOGISTICS_AIC", "LOGISTICS_RPC_URL"
    else:
        return
    live = (os.getenv(env_k) or "").strip()
    url = (os.getenv(url_k) or "").strip()
    if live:
        c["aic"] = live
        if isinstance(c.get("acs"), dict):
            c["acs"]["aic"] = live
    if url:
        c["endpoint"] = url


def _acs_to_candidate(acs: dict[str, Any], *, source: str) -> dict[str, Any]:
    eps = acs.get("endPoints") or []
    url = ""
    if eps and isinstance(eps[0], dict):
        url = str(eps[0].get("url") or "")
    name = str(acs.get("name") or "")
    aic = str(acs.get("aic") or "")
    agent_id = "unknown"
    # 仅认供应商（勿用 endswith「智能体A」——会误伤「采购智能体A」）
    if _aic_matches(aic, _SUPPLIER_AIC_MARKERS["supplier-a"]) or (
        "供应商" in name and "A" in name and "采购" not in name
    ):
        agent_id = "supplier-a"
    elif _aic_matches(aic, _SUPPLIER_AIC_MARKERS["supplier-b"]) or (
        "供应商" in name and "B" in name and "采购" not in name
    ):
        agent_id = "supplier-b"
    elif _aic_matches(aic, _SUPPLIER_AIC_MARKERS["supplier-c"]) or (
        "供应商" in name and "C" in name and "采购" not in name
    ):
        agent_id = "supplier-c"
    elif _aic_matches(aic, _LOGISTICS_AIC_MARKERS) or "物流" in name:
        agent_id = "logistics"

    return {
        "agent_id": agent_id,
        "aic": acs.get("aic") or "",
        "name": name,
        "description": (acs.get("description") or "")[:280],
        "endpoint": url,
        "skills": [s.get("id") or s.get("name") for s in (acs.get("skills") or []) if isinstance(s, dict)],
        "source": source,
        "acs": {"name": name, "aic": acs.get("aic"), "version": acs.get("version")},
    }


def _env_peer_supplier_candidates() -> list[dict[str, Any]]:
    """本域 env 登记的供应 A/B/C（证书 CN + 公网 RPC），作平台空结果时的明示降级。"""
    rows: list[tuple[str, str, str, str]] = [
        ("supplier-a", "SUPPLIER_A_AIC", "SUPPLIER_A_RPC_URL", "供应商A（本域登记）"),
        ("supplier-b", "SUPPLIER_B_AIC", "SUPPLIER_B_RPC_URL", "供应商B（本域登记）"),
        ("supplier-c", "SUPPLIER_C_AIC", "SUPPLIER_C_RPC_URL", "供应商C（本域登记）"),
    ]
    out: list[dict[str, Any]] = []
    for aid, aic_k, url_k, name in rows:
        aic = (os.getenv(aic_k) or "").strip()
        url = (os.getenv(url_k) or "").strip()
        if not aic or not url:
            continue
        c: dict[str, Any] = {
            "agent_id": aid,
            "aic": aic,
            "name": name,
            "description": "env peer fill after platform ADP empty",
            "endpoint": url,
            "skills": [],
            "source": "env_peer_fill",
            "source_label": "本域登记（平台未命中降级）",
            "degrade": True,
            "acs": {"name": name, "aic": aic},
        }
        _bind_live_peer(c)
        out.append(c)
    return out


def load_local_supplier_acs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fname in _LOCAL_SUPPLIER_ACS:
        path = _ACS_DIR / fname
        if not path.is_file():
            continue
        acs = json.loads(path.read_text(encoding="utf-8"))
        # filename 优先定 agent_id（勿用 "supplier-a" in fname：会误匹配 supplier-agent-*）
        if "supplier-agent-a" in fname or fname.startswith("supplier-a."):
            agent_id = "supplier-a"
        elif "supplier-agent-b" in fname or fname.startswith("supplier-b."):
            agent_id = "supplier-b"
        elif "supplier-agent-c" in fname or fname.startswith("supplier-c."):
            agent_id = "supplier-c"
        else:
            continue
        cand = _acs_to_candidate(acs, source="local_acs_list")
        cand["agent_id"] = agent_id
        key = {"supplier-a": "SUPPLIER_A_AIC", "supplier-b": "SUPPLIER_B_AIC", "supplier-c": "SUPPLIER_C_AIC"}[agent_id]
        url_key = {
            "supplier-a": "SUPPLIER_A_RPC_URL",
            "supplier-b": "SUPPLIER_B_RPC_URL",
            "supplier-c": "SUPPLIER_C_RPC_URL",
        }[agent_id]
        if os.getenv(key):
            cand["aic"] = os.getenv(key, cand["aic"])
        if os.getenv(url_key):
            cand["endpoint"] = os.getenv(url_key, cand["endpoint"])
        out.append(cand)
    return out


def _platform_discover_urls(base: str) -> list[str]:
    """梧桐 Discovery Server 2.2 路径为 /acps-adp-v2/discover；兼容旧 /discover。"""
    base = base.rstrip("/")
    # 环境可覆盖：ACPS_DISCOVER_PATH=/acps-adp-v2/discover
    custom = (os.getenv("ACPS_DISCOVER_PATH") or "").strip()
    if custom:
        if custom.startswith("http"):
            return [custom]
        return [f"{base}{custom if custom.startswith('/') else '/' + custom}"]
    return [
        f"{base}/acps-adp-v2/discover",
        f"{base}/discover",
    ]


def _iter_agent_skill_hits(result: dict[str, Any]) -> list[tuple[str, str, int]]:
    """从 agents / routes 抽出 (aic, skillId, ranking)。规范：agentSkills.aic → acsMap。"""
    hits: list[tuple[str, str, int]] = []

    def _from_groups(groups: Any) -> None:
        if not isinstance(groups, list):
            return
        for group in groups:
            if not isinstance(group, dict):
                continue
            skills = group.get("agentSkills") or group.get("agent_skills") or []
            if not isinstance(skills, list):
                continue
            for sk in skills:
                if not isinstance(sk, dict):
                    continue
                aic = str(sk.get("aic") or "").strip()
                if not aic:
                    continue
                sid = str(sk.get("skillId") or sk.get("skill_id") or "")
                try:
                    rank = int(sk.get("ranking") or 0)
                except (TypeError, ValueError):
                    rank = 0
                hits.append((aic, sid, rank))

    _from_groups(result.get("agents") or [])
    for route in result.get("routes") or []:
        if isinstance(route, dict):
            _from_groups(route.get("agentGroups") or route.get("agent_groups") or [])
    # ranking 越小越靠前
    hits.sort(key=lambda x: x[2])
    return hits


def _extract_platform_acs(body: dict[str, Any]) -> list[dict[str, Any]]:
    """按 ADP 规范：agentSkills → acsMap；再并入 acsMap 余项。"""
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    acs_map = result.get("acsMap") or result.get("acs_map") or body.get("acsMap") or {}
    if not isinstance(acs_map, dict):
        acs_map = {}

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1) 命中技能优先（与叮当/发现 Agent 同一套关联方式）
    for aic, skill_id, _rank in _iter_agent_skill_hits(result):
        if aic in seen:
            continue
        acs = acs_map.get(aic)
        if not isinstance(acs, dict):
            # acsMap 偶发缺条目时仍保留 aic，后续靠本地 AIC 对齐
            acs = {"aic": aic, "name": "", "skills": [{"id": skill_id}] if skill_id else []}
        row = dict(acs)
        row.setdefault("aic", aic)
        if skill_id:
            row["_matched_skill"] = skill_id
        seen.add(aic)
        out.append(row)

    # 2) acsMap 其余条目（语义相关上下文）
    for aic, acs in acs_map.items():
        key = str(aic)
        if key in seen or not isinstance(acs, dict):
            continue
        row = dict(acs)
        row.setdefault("aic", key)
        seen.add(key)
        out.append(row)
    return out


def _is_supplier_candidate(c: dict[str, Any]) -> bool:
    name = str(c.get("name") or "")
    aic = str(c.get("aic") or "")
    ep = str(c.get("endpoint") or "")
    skills = " ".join(str(s) for s in (c.get("skills") or []))
    if c.get("agent_id", "").startswith("supplier-"):
        return True
    if any(
        _aic_matches(aic, markers)
        for markers in _SUPPLIER_AIC_MARKERS.values()
    ):
        return True
    if "供应商" in name and "采购" not in name:
        return True
    if any(p in ep for p in (":8011", ":8013", ":8014")):
        return True
    if "agentlink.supplier" in skills:
        return True
    return False


def _prefer_supplier_candidates(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """平台会返回买家/物流/发现Agent；采购发现只留供应商。"""
    suppliers = [c for c in cands if _is_supplier_candidate(c)]
    return suppliers


def _normalize_supplier_id(c: dict[str, Any]) -> None:
    ep = c.get("endpoint") or ""
    aic = str(c.get("aic") or "")
    skills = " ".join(str(s) for s in (c.get("skills") or []))
    matched = ""
    if isinstance(c.get("acs"), dict):
        matched = str(c["acs"].get("_matched_skill") or "")
    blob = f"{skills} {matched}"
    if ":8011" in ep or _aic_matches(aic, _SUPPLIER_AIC_MARKERS["supplier-a"]):
        c["agent_id"] = "supplier-a"
    elif ":8013" in ep or _aic_matches(aic, _SUPPLIER_AIC_MARKERS["supplier-b"]):
        c["agent_id"] = "supplier-b"
    elif ":8014" in ep or _aic_matches(aic, _SUPPLIER_AIC_MARKERS["supplier-c"]):
        c["agent_id"] = "supplier-c"
    elif "agentlink.supplier.scarce" in blob:
        c["agent_id"] = "supplier-c"
    elif "agentlink.supplier.custom" in blob:
        c["agent_id"] = "supplier-b"
    elif "agentlink.supplier.quote" in blob:
        c["agent_id"] = "supplier-a"
    _bind_live_peer(c)


async def _post_discover(url: str, query: str, *, limit: int) -> dict[str, Any]:
    payload = {"type": "explicit", "query": query, "limit": limit}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 404:
            raise httpx.HTTPStatusError(
                f"404 Not Found for url '{url}'",
                request=resp.request,
                response=resp,
            )
        resp.raise_for_status()
        body = resp.json()
    return body if isinstance(body, dict) else {}


# 实测可命中平台目录的兜底查询（须覆盖 A/B/C 技能；C 对 scarce 中文/英文更稳）
_FALLBACK_QUERIES = (
    "工业原料供应商 报价",
    "agentlink.supplier.quote",
    "agentlink.supplier.custom-quote",
    "agentlink.supplier.scarce-quote",
    "库存紧张 供应商",
    "substitute scarce",
    "采联供应商智能体C",
    "采联供应商智能体B",
    "采联供应商智能体A",
    "采联供应商智能体",
    "座椅面料 软装 供应商",
)


async def discover_suppliers(
    query: str = "工业原料供应商 报价 议价 座椅配件",
    *,
    limit: int = 5,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    """平台 ADP 优先；失败则本地 ACS List。"""
    cache_key = f"{(query or '').strip()}|{limit}"
    if not bypass_cache and _CACHE_TTL_SEC > 0:
        hit = _DISCOVER_CACHE.get(cache_key)
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_SEC:
            report(f"发现缓存命中（{_CACHE_TTL_SEC:.0f}s TTL）· 跳过重复平台检索", phase="adp")
            cached = dict(hit[1])
            cached["cache_hit"] = True
            return cached

    base = (os.getenv("ACPS_DISCOVERY_URL") or "").rstrip("/")
    platform_error = None
    platform_candidates: list[dict[str, Any]] = []
    used_url: str | None = None
    t0 = time.monotonic()

    if base:
        report("正在连接梧桐发现服务器（ADP）…", phase="adp")
        queries: list[str] = []
        for q in (query, *_FALLBACK_QUERIES):
            q = (q or "").strip()
            if q and q not in queries:
                queries.append(q)
        last_err: str | None = None
        for url in _platform_discover_urls(base):
            got_any = False
            report(f"发现入口：{url}", phase="adp")
            for q in queries:
                report(f"正在梧桐平台检索符合条件的智能体：「{q[:42]}」…", phase="adp")
                try:
                    body = await _post_discover(url, q, limit=max(limit, 12))
                except httpx.HTTPStatusError as exc:
                    last_err = str(exc)
                    if exc.response is not None and exc.response.status_code == 404:
                        report("该发现路径不存在，尝试兼容路径…", phase="adp")
                        break  # try next url path
                    report(f"平台检索暂时失败：{exc}", phase="adp")
                    continue
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    report(f"平台检索异常：{exc}", phase="adp")
                    continue
                used_url = url
                got_any = True
                extracted = _extract_platform_acs(body)
                hit_names: list[str] = []
                for acs in extracted:
                    cand = _acs_to_candidate(acs, source="platform_adp")
                    if acs.get("_matched_skill"):
                        cand.setdefault("acs", {})
                        if isinstance(cand["acs"], dict):
                            cand["acs"]["_matched_skill"] = acs["_matched_skill"]
                        skills = list(cand.get("skills") or [])
                        if acs["_matched_skill"] not in skills:
                            skills.insert(0, acs["_matched_skill"])
                        cand["skills"] = skills
                    _normalize_supplier_id(cand)
                    platform_candidates.append(cand)
                    if _is_supplier_candidate(cand) and cand.get("name"):
                        hit_names.append(str(cand["name"]))
                if hit_names:
                    uniq = list(dict.fromkeys(hit_names))
                    report("平台命中供应商：" + "、".join(uniq[:5]), phase="adp")
                # 凑齐 supplier-a/b/c 再停；禁止「只命中 A/B」就结束（否则 C 永远走本地容灾）
                known_ids = {
                    str(c.get("agent_id"))
                    for c in platform_candidates
                    if str(c.get("agent_id") or "").startswith("supplier-")
                }
                if {"supplier-a", "supplier-b", "supplier-c"}.issubset(known_ids):
                    report("平台已凑齐供应商 A/B/C", phase="adp")
                    break
            # queries 已跑完；换下一兼容 path（通常仅一条）
            if got_any:
                break
        # 去重（按 aic）
        dedup: dict[str, dict[str, Any]] = {}
        for c in platform_candidates:
            key = str(c.get("aic") or c.get("name") or id(c))
            prev = dedup.get(key)
            if prev is None or (not prev.get("name") and c.get("name")):
                dedup[key] = c
        platform_candidates = list(dedup.values())
        if not platform_candidates and last_err:
            platform_error = last_err
    else:
        report("未配置梧桐发现地址（ACPS_DISCOVERY_URL），无法发现", phase="adp")
        platform_error = platform_error or "ACPS_DISCOVERY_URL not set"

    # 只认平台 ADP：找不到就是没有（不再用本地 ACS 黄页兜底/补齐）
    candidates: list[dict[str, Any]] = []
    source = "platform_adp"
    if platform_candidates:
        report("正在整理平台候选…", phase="adp")
        for c in platform_candidates:
            _normalize_supplier_id(c)
            c["source"] = "platform_adp"
            c["source_label"] = "平台发现"
            c["degrade"] = False
        candidates = _prefer_supplier_candidates(platform_candidates)
        candidates = [
            c
            for c in candidates
            if str(c.get("agent_id") or "").startswith("supplier-")
        ]
        if not candidates and platform_error is None:
            platform_error = "platform returned no supplier ACS (filtered)"
            source = "platform_adp_empty"
            report("平台有返回，但过滤后无供应商候选", phase="adp")
    else:
        source = "platform_adp_empty"
        report(
            "平台未命中供应商" + (f"：{platform_error}" if platform_error else ""),
            phase="adp",
        )

    # 平台空/过滤空：用本域已登记供应（证书 CN + RPC）作明示降级，避免演示卡死
    # 不伪装成 platform_adp；source 标注 env_peer_fill
    allow_fill = (os.getenv("DISCOVERY_ALLOW_ENV_FILL") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    degrade = False
    degrade_reason = None
    if allow_fill and not candidates:
        filled = _env_peer_supplier_candidates()
        if filled:
            candidates = filled
            degrade = True
            degrade_reason = platform_error or "platform_adp_empty"
            source = "env_peer_fill"
            report(
                f"平台未命中，已用本域登记供应兜底（A/B/C）· 原因：{degrade_reason}",
                phase="adp",
            )

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    report(f"发现完成 · {source} · 候选 {len(candidates)} · {elapsed_ms}ms", phase="adp")
    result = {
        "query": query,
        "source": source,
        "platform_error": platform_error,
        "candidates": candidates[:limit],
        "discovery_url": used_url or base or None,
        "degrade": degrade,
        "degrade_reason": degrade_reason,
        "elapsed_ms": elapsed_ms,
        "cache_hit": False,
    }
    # 空结果不缓存，避免一次瞬时失败把后续 60s 发现全部打空
    if _CACHE_TTL_SEC > 0 and candidates:
        _DISCOVER_CACHE[cache_key] = (time.monotonic(), dict(result))
    return result


def _is_logistics_candidate(c: dict[str, Any]) -> bool:
    name = str(c.get("name") or "")
    aic = str(c.get("aic") or "")
    ep = str(c.get("endpoint") or "")
    skills = " ".join(str(s) for s in (c.get("skills") or []))
    matched = ""
    if isinstance(c.get("acs"), dict):
        matched = str(c["acs"].get("_matched_skill") or "")
    blob = f"{skills} {matched}".lower()
    if c.get("agent_id") == "logistics":
        return True
    if _aic_matches(aic, _LOGISTICS_AIC_MARKERS):
        return True
    if "物流" in name:
        return True
    if ":8015" in ep:
        return True
    if "logistics" in blob or "shipping" in blob:
        return True
    return False


def _normalize_logistics_id(c: dict[str, Any]) -> None:
    ep = str(c.get("endpoint") or "")
    aic = str(c.get("aic") or "")
    if (
        ":8015" in ep
        or _aic_matches(aic, _LOGISTICS_AIC_MARKERS)
        or "物流" in str(c.get("name") or "")
    ):
        c["agent_id"] = "logistics"
    _bind_live_peer(c)


def _configured_logistics_peer() -> dict[str, Any] | None:
    """本域配置的物流端点（非 ACS 黄页兜底；平台未命中时供应侧仍可询运）。"""
    url = (os.getenv("LOGISTICS_RPC_URL") or "").strip()
    aic = (os.getenv("LOGISTICS_AIC") or "").strip()
    if not url or not aic:
        # 演示默认本机物流（AIC 须与 logistics 证书 CN 一致）
        url = url or "https://127.0.0.1:8015/rpc"
        aic = aic or "1.2.156.3088.1.BUPT.2HY2P9.JOBNF9.39B1TM.0ALR"
    return {
        "agent_id": "logistics",
        "aic": aic,
        "name": "采联物流智能体",
        "description": "configured logistics peer",
        "endpoint": url,
        "skills": ["agentlink.logistics.shipping-quote"],
        "source": "configured_peer",
        "source_label": "本域配置物流",
        "degrade": True,
        "acs": {"name": "采联物流智能体", "aic": aic},
    }


_LOGISTICS_FALLBACK_QUERIES = (
    "物流 运费报价",
    "agentlink.logistics.shipping-quote",
    "采联物流智能体",
    "shipping quote logistics",
)


async def discover_logistics(
    query: str = "物流 运费报价 agentlink.logistics",
    *,
    limit: int = 3,
    bypass_cache: bool = False,
    allow_configured_peer: bool = True,
) -> dict[str, Any]:
    """供应商被动技能：ADP 发现物流；平台未命中时可回退本域配置端点。"""
    cache_key = f"logistics|{(query or '').strip()}|{limit}"
    if not bypass_cache and _CACHE_TTL_SEC > 0:
        hit = _DISCOVER_CACHE.get(cache_key)
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_SEC:
            cached = dict(hit[1])
            cached["cache_hit"] = True
            return cached

    base = (os.getenv("ACPS_DISCOVERY_URL") or "").rstrip("/")
    platform_error = None
    platform_candidates: list[dict[str, Any]] = []
    used_url: str | None = None
    t0 = time.monotonic()

    if base:
        report("供应侧发现物流：连接梧桐 ADP…", phase="adp")
        queries: list[str] = []
        for q in (query, *_LOGISTICS_FALLBACK_QUERIES):
            q = (q or "").strip()
            if q and q not in queries:
                queries.append(q)
        last_err: str | None = None
        for url in _platform_discover_urls(base):
            got_any = False
            for q in queries:
                try:
                    body = await _post_discover(url, q, limit=max(limit, 8))
                except httpx.HTTPStatusError as exc:
                    last_err = str(exc)
                    if exc.response is not None and exc.response.status_code == 404:
                        break
                    continue
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    continue
                used_url = url
                got_any = True
                for acs in _extract_platform_acs(body):
                    cand = _acs_to_candidate(acs, source="platform_adp")
                    if acs.get("_matched_skill"):
                        cand.setdefault("acs", {})
                        if isinstance(cand["acs"], dict):
                            cand["acs"]["_matched_skill"] = acs["_matched_skill"]
                        skills = list(cand.get("skills") or [])
                        if acs["_matched_skill"] not in skills:
                            skills.insert(0, acs["_matched_skill"])
                        cand["skills"] = skills
                    _normalize_logistics_id(cand)
                    platform_candidates.append(cand)
                if any(_is_logistics_candidate(c) for c in platform_candidates):
                    report("平台已命中物流候选", phase="adp")
                    break
            if got_any:
                break
        dedup: dict[str, dict[str, Any]] = {}
        for c in platform_candidates:
            key = str(c.get("aic") or c.get("name") or id(c))
            prev = dedup.get(key)
            if prev is None or (not prev.get("name") and c.get("name")):
                dedup[key] = c
        platform_candidates = list(dedup.values())
        if not platform_candidates and last_err:
            platform_error = last_err
    else:
        platform_error = "ACPS_DISCOVERY_URL not set"

    logistics = [c for c in platform_candidates if _is_logistics_candidate(c)]
    for c in logistics:
        _normalize_logistics_id(c)
        c["source"] = "platform_adp"
        c["source_label"] = "平台发现"
        c["degrade"] = False

    degrade = False
    degrade_reason = None
    source = "platform_adp"
    if not logistics:
        source = "platform_adp_empty"
        if allow_configured_peer:
            peer = _configured_logistics_peer()
            if peer:
                logistics = [peer]
                source = "configured_peer"
                degrade = True
                degrade_reason = platform_error or "platform returned no logistics"
                report(f"物流 ADP 未命中，使用本域配置端点 · {peer.get('endpoint')}", phase="adp")
        elif platform_error:
            report(f"物流发现失败：{platform_error}", phase="adp")

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    result = {
        "query": query,
        "source": source,
        "platform_error": platform_error,
        "candidates": logistics[:limit],
        "discovery_url": used_url or base or None,
        "degrade": degrade,
        "degrade_reason": degrade_reason,
        "elapsed_ms": elapsed_ms,
        "cache_hit": False,
    }
    if _CACHE_TTL_SEC > 0:
        _DISCOVER_CACHE[cache_key] = (time.monotonic(), dict(result))
    return result
