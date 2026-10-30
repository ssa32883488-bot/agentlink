# -*- coding: utf-8 -*-
"""Batch-regenerate report architecture / diagram figures via custom-imagegen CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"f:\code\智能体协议")
OUT = ROOT / "outputs" / "custom-imagegen"
SCRIPT = Path(r"C:\Users\32081\.codex\skills\custom-imagegen\scripts\custom_image_gen.py")
BASE_URL = "https://api.maxopenapi.com/v1"
MODEL_PREFERRED = ("gpt-image-2", "gpt-image-2.5-flare", "gpt-image-1.5")

STYLE = (
    "Clean technical architecture diagram for a Chinese academic engineering report. "
    "Flat vector, white background, teal and slate accents, thin precise arrows, "
    "readable Chinese labels, high contrast print-friendly, no purple glow, no 3D, "
    "no photorealistic clutter, no logos, no watermark, no decorative icons overload."
)

FIGURES = [
    {
        "out": "ch2-requirements.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图2-1 采联场景需求分解. "
            "Three linked columns: 痛点 (协议碎片化/跨云难互通/访问不可证) → "
            "能力 (ADP发现/AIP互联/AMP访问/HITL门控) → "
            "验收 (注册发现互联访问四项可核验). Horizontal flow left to right."
        ),
    },
    {
        "out": "ch2-usecase.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图2-2 采销目标场景. "
            "Main horizontal path: 发现→短名单HITL→并行询价→比价决策→订单草案. "
            "Two branch lanes below: 比价支路 and 组群竞价支路 converging to 下单. "
            "Actors: 采购Leader, 供应Partner×3, 物流Partner."
        ),
    },
    {
        "out": "ch3-v2-architecture.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图3-1 采联五层架构 commerce_v2. "
            "Five stacked layers top to bottom: "
            "①对话与HITL层 ②采购编排(normal/group) ③协议平面 AIC/ACS/ADP/AIP/AMP "
            "④运行时 Python/Java ⑤双云基础设施 腾讯云采购+物流 / 阿里云供应. "
            "Vertical arrows between layers; side note 国标骨架不改."
        ),
    },
    {
        "out": "ch3-v2-reuse-innovate.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图3-2 开源复用与自主创新边界. "
            "Left box 开源复用: acps-sdk, AIP报文, 梧桐Registry/CA/Discovery/Kafka. "
            "Right box 自主创新: 双侧AMP对账, HITL四态, 可解释容灾, 双云编排, 竞拍并行优化. "
            "Center divider labeled 边界: 不改国标骨架."
        ),
    },
    {
        "out": "ch3-v2-normal-path.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图3-3 普通采购路径. "
            "Left-to-right sequence boxes: create_case → discover(platform_adp) → "
            "AskUser短名单 → Gate确认 → 并行RFQ(AIP) → 比价/下单. "
            "Annotate AskUser断点 and Gate in orange outline."
        ),
    },
    {
        "out": "ch3-v2-group-path.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图3-4 组群竞价路径. "
            "Flow: RFQ完成 → decide_auction → Group invite并行 → 盲拍/TCO → "
            "选商 ORDER_DRAFT. Side annotation: Group优先, 失败显式回退 transport=rpc."
        ),
    },
    {
        "out": "ch4-v2-dual-cloud.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图4-1 双云六体部署拓扑. "
            "Left cloud 腾讯云: buyer-a, buyer-b, logistics with UI ports 8090/8092/8095. "
            "Right cloud 阿里云: supplier-a/b/c with UI 8091/8093/8094. "
            "Center hub 梧桐平台 ADP/AIP/AMP. Cross-cloud mTLS arrows."
        ),
    },
    {
        "out": "ch4-v2-milestones.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图4-2 commerce_v2 实施里程碑. "
            "Horizontal timeline 2026-09-15 to 2026-10-20 with milestones: "
            "需求拆解, 开源适配, AIP兼容, 梧桐对接, 双云联调, 取证材料. "
            "Clean gantt-like bars, not cluttered."
        ),
    },
    {
        "out": "ch4-module-flow.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图4-2 模块分层与数据流. "
            "Boxes: UI控制台 → 编排flow_service → ADP发现 / AIP RPC / Group MQ → "
            "AMP Kafka → 证据落盘. Bottom open-source base acps-sdk + wit."
        ),
    },
    {
        "out": "ch4-schedule.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 图4-1 开发周期甘特. "
            "Gantt chart 2026-09-15～10-20 phases P0需求 P1开源适配 P2协议 P3平台 "
            "P4联调 P5材料. Clean rows, soft teal bars."
        ),
    },
    {
        "out": "ch4-wutong-seq.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 梧桐接入全流程. "
            "Four large numbered steps in a row: 1注册ACS/AIC 2发现ADP "
            "3互联AIP 4访问AMP. Under each step a short Chinese subtitle."
        ),
    },
    {
        "out": "ch4-procurement-seq.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 采购协同主路径时序. "
            "Swimlane-style sequence: 采购对话 → 平台发现 → HITL → 并行询价 → "
            "竞价或下单 → AMP留痕. Clear actor columns."
        ),
    },
    {
        "out": "ch5-v2-kpi-dashboard.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 采联联调成效KPI. "
            "Big numbers grid: AMP Access 349, Message 328, Tasks 151, "
            "协议成功率 91%, 报价准确率 95.2%, ADP命中 93.8%, 竞拍 7.6s vs 30-120s, "
            "RPC 311ms. Small sparkline 27 43 44 32 9."
        ),
    },
    {
        "out": "ch5-v2-latency-before-after.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 竞拍时延优化前后对照. "
            "Left column 优化前: 串行invite, 空等45s, 串行RPC, 墙钟30-120s+. "
            "Right column 优化后: 并行invite, 早停, 并行RPC 311ms, 墙钟7.6s. "
            "Large arrow 约4-15× between columns."
        ),
    },
    {
        "out": "ch5-v2-dual-path-outcomes.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 双路径成效. "
            "Two parallel vertical lanes: 普通询价 (platform_adp→RFQ→比价) and "
            "组群竞价 (auction→TCO→ORDER_DRAFT). Bottom shared outcomes badges: "
            "可复现, 可解释回退, AMP可审计."
        ),
    },
    {
        "out": "ch5-v2-validation.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 必要验证完成情况. "
            "Four checklist cards: 注册已完成, 发现已完成, 互联已完成, "
            "访问工程侧已完成(后台截图待补). Checkmarks in teal."
        ),
    },
    {
        "out": "ch6-v2-roadmap.png",
        "size": "1536x1024",
        "prompt": (
            f"{STYLE} Title: 总结与展望路线. "
            "Three horizontal lanes: 标准化落地, 功能拓展, 工程推广. "
            "Columns 近期 / 中期 with concrete Chinese bullets. "
            "Footer note GitHub开源维护."
        ),
    },
]


def pick_model() -> str:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "models", "--json", "--base-url", BASE_URL],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit("models query failed; set CUSTOM_IG_API_KEY and retry")
    data = json.loads(r.stdout)
    image_models = data.get("image_models") or data.get("models") or []
    names = []
    for m in image_models:
        if isinstance(m, str):
            names.append(m)
        elif isinstance(m, dict):
            names.append(str(m.get("id") or m.get("name") or ""))
    for pref in MODEL_PREFERRED:
        if pref in names:
            return pref
    if names:
        return names[0]
    raise SystemExit(f"no image models: {data}")


def generate(model: str, item: dict) -> None:
    out = OUT / item["out"]
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(SCRIPT),
        "generate",
        "--prompt",
        item["prompt"],
        "--model",
        model,
        "--base-url",
        BASE_URL,
        "--size",
        item["size"],
        "--timeout",
        "300",
        "--force",
        "--out",
        str(out),
    ]
    print("==>", item["out"], "model=", model)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(f"failed {item['out']}")
    if not out.exists() or out.stat().st_size < 10_000:
        raise SystemExit(f"bad output {out}")
    print("ok", out, out.stat().st_size)


def main() -> None:
    model = pick_model()
    print("using model", model)
    only = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    for item in FIGURES:
        if only and item["out"] not in only:
            continue
        generate(model, item)
    print("ALL_DONE")


if __name__ == "__main__":
    main()
