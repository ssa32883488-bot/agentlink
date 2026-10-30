# -*- coding: utf-8 -*-
"""Generate Chapter-4 technical diagrams with matplotlib (no external image API)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(r"f:\code\智能体协议\outputs\custom-imagegen")
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _box(ax, xy, w, h, text, fc="#E8F1FB", ec="#2F5D8C", fs=9, lw=1.2):
    x, y = xy
    p = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=lw, edgecolor=ec, facecolor=fc,
    )
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color="#1A1A1A", wrap=True)


def _arrow(ax, a, b):
    ax.add_patch(
        FancyArrowPatch(
            a, b, arrowstyle="-|>", mutation_scale=12,
            linewidth=1.2, color="#334155",
        )
    )


def gen_module_flow():
    fig, ax = plt.subplots(figsize=(14, 7.5), dpi=160)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("图4-2　采联 AgentLink 模块分层与数据流", fontsize=14, pad=12, fontweight="bold")

    # layers
    layers = [
        (0.4, 6.4, 13.2, 1.3, "#FFF7E6", "#B45309", "表现层　UI 控制台 / 座椅商城\n(ui/static · 六体独立门户 · 协作面板)"),
        (0.4, 4.7, 13.2, 1.3, "#ECFDF5", "#047857", "业务编排层　对话 Wit · 采购案状态机 · HITL · 工具网关 · scheme_planner\n(commerce/chat_* · procurement_case · hitl_gate · flow_service · gateway)"),
        (0.4, 3.0, 13.2, 1.3, "#EFF6FF", "#1D4ED8", "协议平面　ADP 发现 · AIP RPC/组群 · AMP Access/Message\n(commerce/discovery · aip_client_util · partner_app · amp_log · group_mq)"),
        (0.4, 1.3, 13.2, 1.3, "#F5F3FF", "#6D28D9", "运行与部署　双云 Agent 进程 · mTLS/证书 · Kafka/MQ · SQLite ERP\n(agents/* · mtls · deploy_remote · acs/*.acs.json)"),
    ]
    for x, y, w, h, fc, ec, t in layers:
        _box(ax, (x, y), w, h, t, fc=fc, ec=ec, fs=10)

    # side callouts
    _box(ax, (0.6, 0.15), 4.0, 0.9, "开源基座\nacps-sdk 2.2 / wit-framework", fc="#F8FAFC", ec="#64748B", fs=8)
    _box(ax, (5.0, 0.15), 4.0, 0.9, "梧桐平台\nRegistry / Discovery / Kafka / MQ", fc="#F8FAFC", ec="#64748B", fs=8)
    _box(ax, (9.4, 0.15), 4.0, 0.9, "自主业务\n六体采销协同 · TCO · 证据链", fc="#F8FAFC", ec="#64748B", fs=8)

    fig.tight_layout()
    path = OUT / "ch4-module-flow.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", path)


def gen_wutong_seq():
    fig, ax = plt.subplots(figsize=(14, 8), dpi=160)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title("图4-3　梧桐接入全流程（注册→发现→互联→访问）", fontsize=14, pad=12, fontweight="bold")

    actors = [
        (1.2, "成员/运维"),
        (4.0, "采联六体"),
        (7.0, "梧桐平台"),
        (10.2, "Kafka/MQ"),
        (12.6, "对端Partner"),
    ]
    for x, name in actors:
        ax.text(x, 8.4, name, ha="center", fontsize=10, fontweight="bold")
        ax.plot([x, x], [0.6, 8.1], color="#CBD5E1", lw=1.2, ls="--")

    steps = [
        (7.6, "① ACS 提交 / AIC 回填\nfinalize_acs · enroll_platform", 1.2, 7.0),
        (6.7, "② ADP Discover\nPOST /acps-adp-v2/discover", 4.0, 7.0),
        (5.8, "③ 候选绑定 live AIC/RPC\nsource=platform_adp", 4.0, 4.0),
        (4.9, "④ AIP Start 结构化任务\naip_start_structured", 4.0, 12.6),
        (4.0, "⑤ Partner /rpc 回执\n确定性 graph", 12.6, 4.0),
        (3.1, "⑥ AMP record_access\nsend/receive 双侧", 4.0, 10.2),
        (2.2, "⑦ 组群竞价可选\nMQ 失败→transport=rpc", 4.0, 10.2),
        (1.3, "⑧ metrics / 证据落盘\n对账 taskId", 4.0, 1.2),
    ]
    for y, text, x0, x1 in steps:
        ax.annotate(
            "",
            xy=(x1, y),
            xytext=(x0, y),
            arrowprops=dict(arrowstyle="-|>", color="#2563EB", lw=1.4),
        )
        mid = (x0 + x1) / 2
        ax.text(mid, y + 0.25, text, ha="center", va="bottom", fontsize=8, color="#0F172A")

    fig.tight_layout()
    path = OUT / "ch4-wutong-seq.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", path)


def gen_schedule():
    fig, ax = plt.subplots(figsize=(14, 5.2), dpi=160)
    ax.set_xlim(0, 36)  # days from 9/15 inclusive ~36 days to 10/20
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("图4-1　开发周期甘特示意（2026-09-15～2026-10-20）", fontsize=14, pad=10, fontweight="bold")

    phases = [
        (0, 7, "P0 立项与需求拆解\n9/15–9/21", "#DBEAFE", 4.2),
        (7, 7, "P1 开源适配改造\n9/22–9/28", "#D1FAE5", 3.2),
        (14, 7, "P2 AIP 标准兼容\n9/29–10/5", "#EDE9FE", 2.2),
        (21, 7, "P3 梧桐对接调试\n10/6–10/12", "#FFEDD5", 1.2),
        (28, 8, "P4 全功能联调测试\n10/13–10/20", "#FEE2E2", 0.2),
    ]
    for x, w, label, fc, y in phases:
        _box(ax, (x + 0.3, y), w - 0.5, 0.85, label, fc=fc, ec="#334155", fs=9)

    # week ticks
    for i, lab in enumerate(["9/15", "9/22", "9/29", "10/6", "10/13", "10/20"]):
        ax.plot([i * 7, i * 7], [5.2, 5.35], color="#64748B")
        ax.text(i * 7, 5.45, lab, ha="center", fontsize=8, color="#475569")
    ax.plot([0, 35], [5.2, 5.2], color="#94A3B8", lw=1)

    ax.text(
        18, 5.85,
        "里程碑：M1 六体骨架可启动 · M2 跨云 AIP 通 · M3 平台发现命中 · M4 双链路证据齐备",
        ha="center", fontsize=9, color="#1E293B",
    )
    fig.tight_layout()
    path = OUT / "ch4-schedule.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", path)


if __name__ == "__main__":
    gen_schedule()
    gen_module_flow()
    gen_wutong_seq()
