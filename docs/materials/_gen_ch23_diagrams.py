# -*- coding: utf-8 -*-
"""Chapter 2/3 support diagrams."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(r"f:\code\智能体协议\outputs\custom-imagegen")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _box(ax, xy, w, h, text, fc, ec, fs=9):
    x, y = xy
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
            linewidth=1.2, edgecolor=ec, facecolor=fc,
        )
    )
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)


def gen_ch2_requirements():
    fig, ax = plt.subplots(figsize=(14, 7), dpi=160)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("图2-1　采联场景需求分解：痛点→能力→验收", fontsize=14, fontweight="bold", pad=10)

    _box(ax, (0.4, 5.8), 3.0, 1.6, "行业痛点\n协议碎片\n跨云身份难统一\n联了不可证", "#FEE2E2", "#B91C1C", 9)
    _box(ax, (4.0, 5.8), 3.0, 1.6, "场景诉求\n座椅原料采销\n多家询价比价\n人机确认下单", "#FFEDD5", "#C2410C", 9)
    _box(ax, (7.6, 5.8), 3.0, 1.6, "能力需求\n发现/询价/HITL\n议价·竞价·物流\nAMP 双侧留痕", "#DBEAFE", "#1D4ED8", 9)
    _box(ax, (11.2, 5.8), 2.4, 1.6, "验收门槛\n注册发现\n互联访问", "#DCFCE7", "#15803D", 9)

    for x0, x1 in [(3.4, 4.0), (7.0, 7.6), (10.6, 11.2)]:
        ax.annotate("", xy=(x1, 6.6), xytext=(x0, 6.6),
                    arrowprops=dict(arrowstyle="-|>", color="#334155", lw=1.4))

    rows = [
        (4.4, "功能", "ADP发现 · AIP询价/议价/竞价/物流 · HITL四态 · 对话编排 · 订单激活"),
        (3.2, "性能", "并行≥3家询价 · 发现可refresh · 关键链路可演示窗口完成 · 时延可观测"),
        (2.0, "兼容", "ACS/AIC/ADP/AIP/AMP 不改国标结构 · 跨云 HTTPS RPC · 异构 Partner"),
        (0.8, "可部署", "双云进程 · 脚本化部署/冒烟 · 六体独立控制台 · 证据落盘"),
    ]
    for y, k, v in rows:
        _box(ax, (0.5, y), 1.8, 0.9, k, "#F1F5F9", "#475569", 10)
        _box(ax, (2.5, y), 11.0, 0.9, v, "#FFFFFF", "#94A3B8", 9)

    fig.tight_layout()
    p = OUT / "ch2-requirements.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", p)


def gen_ch2_usecase():
    fig, ax = plt.subplots(figsize=(14, 6.5), dpi=160)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("图2-2　目标场景用例：采购案主路径与支路", fontsize=14, fontweight="bold", pad=10)

    steps = [
        (0.3, "需求录入"),
        (2.1, "平台发现"),
        (3.9, "HITL短名单"),
        (5.7, "并行询价"),
        (7.5, "比价审查"),
        (9.3, "议价/竞价"),
        (11.1, "物流合入"),
        (12.7, "双边确认"),
    ]
    for i, (x, t) in enumerate(steps):
        _box(ax, (x, 4.6), 1.5, 1.0, t, "#E0F2FE", "#0369A1", 8)
        if i < len(steps) - 1:
            ax.annotate("", xy=(steps[i + 1][0], 5.1), xytext=(x + 1.5, 5.1),
                        arrowprops=dict(arrowstyle="-|>", color="#0F172A", lw=1.2))

    _box(ax, (1.5, 2.6), 4.5, 1.2, "支路A 普通询价\nCOMPARE→选商→ORDER_DRAFT", "#ECFDF5", "#047857", 9)
    _box(ax, (7.5, 2.6), 5.0, 1.2, "支路B 组群竞价\nBIDDING→TCO方案→选商", "#FEF3C7", "#B45309", 9)
    _box(ax, (3.5, 0.6), 7.0, 1.2, "横切约束：平台优先发现 · 协议证据链 · reject 无脏数据 · 访问可对账",
         "#F8FAFC", "#475569", 9)

    ax.annotate("", xy=(3.7, 3.8), xytext=(6.4, 4.6),
                arrowprops=dict(arrowstyle="-|>", color="#047857", lw=1.2))
    ax.annotate("", xy=(10.0, 3.8), xytext=(10.0, 4.6),
                arrowprops=dict(arrowstyle="-|>", color="#B45309", lw=1.2))

    fig.tight_layout()
    p = OUT / "ch2-usecase.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", p)


def gen_ch3_protocol():
    fig, ax = plt.subplots(figsize=(14, 6.8), dpi=160)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("图3-3　协议平面选型：五类能力与工程落点", fontsize=14, fontweight="bold", pad=10)

    items = [
        (0.4, "AIC\n身份标识", "证书CN/环境变量\n绑定公网端点", "#DBEAFE"),
        (3.1, "ACS\n能力描述", "acs/*.acs.json\n技能与RPC声明", "#E0E7FF"),
        (5.8, "ADP\n发现", "wt.ioa.pub\nacps-adp-v2", "#CFFAFE"),
        (8.5, "AIP\n交互", "TaskCommand\n/rpc 回执", "#D1FAE5"),
        (11.2, "AMP\n访问", "amp.access\namp.message", "#FEF3C7"),
    ]
    for x, t, d, fc in items:
        _box(ax, (x, 4.4), 2.4, 1.6, t, fc, "#334155", 10)
        _box(ax, (x, 2.4), 2.4, 1.5, d, "#FFFFFF", "#94A3B8", 8)

    _box(ax, (1.5, 0.5), 11.0, 1.3,
         "安全与协同补充：mTLS / 可选身份绑定 · 组群 MQ（可回退 RPC）· 双侧 AMP 同 taskId 对账",
         "#F1F5F9", "#475569", 9)
    fig.tight_layout()
    p = OUT / "ch3-protocol-map.png"
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", p)


if __name__ == "__main__":
    gen_ch2_requirements()
    gen_ch2_usecase()
    gen_ch3_protocol()
