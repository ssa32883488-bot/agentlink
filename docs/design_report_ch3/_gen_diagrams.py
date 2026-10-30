# -*- coding: utf-8 -*-
"""程序化技术插图（架构/框架/时序）。CUSTOM_IG_API_KEY 就绪后可用 imagegen 重渲同主题。"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
import matplotlib

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)


def _box(ax, x, y, w, h, text, fc="#EFF6FF", ec="#1D4ED8", fs=9, tw=None):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                       linewidth=1.4, edgecolor=ec, facecolor=fc)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            wrap=True, color="#0F172A",
            bbox=dict(boxstyle="square,pad=0", fc="none", ec="none") if tw else None)


def _arrow(ax, x1, y1, x2, y2, color="#334155"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=1.5))


def fig_architecture():
    fig, ax = plt.subplots(figsize=(14, 9), dpi=160)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_title("图3-1  采联 AgentLink 多智能体分层互联总体架构", fontsize=14, pad=12, fontweight="bold")

    # Platform
    _box(ax, 0.4, 8.6, 13.2, 1.0,
         "梧桐智能体科研平台　Registry / CA　·　ADP Discovery　·　Kafka AMP　·　组群 MQ（可选）",
         fc="#FEF3C7", ec="#B45309", fs=10)

    # Layer labels
    layers = [
        (7.4, "① 人机交互层　六体独立控制台 · AskUser 断点 · Gate 工单确认", "#FCE7F3", "#BE185D"),
        (6.0, "② 智能体运行时层　采购AB主持/改写　·　供应ABC报价智力　·　物流方案智力", "#E0E7FF", "#4338CA"),
        (4.4, "③ 业务编排层　普通十点路径　·　组群竞价（采购主持）　·　共享订单标识与双边确认", "#DCFCE7", "#166534"),
        (2.8, "④ 协议适配层　AIC/ACS　·　ADP　·　AIP RPC/组群　·　AMP Access/Message　·　mTLS", "#EFF6FF", "#1D4ED8"),
        (1.2, "⑤ 双云部署层　腾讯云：采购A/B + 物流　　阿里云：供应A/B/C　　分库分端", "#F1F5F9", "#475569"),
    ]
    for y, text, fc, ec in layers:
        _box(ax, 0.4, y, 13.2, 1.15, text, fc=fc, ec=ec, fs=10)

    _box(ax, 0.6, 0.15, 4.0, 0.85, "三柱：互联 · 人断点 · 全员够智力", fc="#FEE2E2", ec="#B91C1C", fs=9)
    _box(ax, 5.0, 0.15, 4.2, 0.85, "旧业务全切；保留 ACPs 协议核心", fc="#FFEDD5", ec="#C2410C", fs=9)
    _box(ax, 9.5, 0.15, 4.1, 0.85, "Leader=采购　Partner=供应/物流", fc="#E0F2FE", ec="#0369A1", fs=9)

    fig.tight_layout()
    path = OUT / "fig3-1_architecture.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("WROTE", path)


def fig_framework():
    fig, ax = plt.subplots(figsize=(14, 8), dpi=160)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title("图3-2  协议与业务框架：复用 ACPs / 自研采销双路径", fontsize=14, pad=12, fontweight="bold")

    _box(ax, 0.3, 6.8, 13.4, 1.6,
         "国标 / 开源复用（不改报文骨架）\n"
         "AIC 身份　ACS 描述　ADP 发现　AIP 交互（Task /rpc）　AMP 访问（Kafka）\n"
         "工程依赖：acps-sdk · 平台证书/mTLS · Discovery · amp.access / amp.message",
         fc="#EEF2FF", ec="#3730A3", fs=10)

    _box(ax, 0.3, 3.6, 6.4, 2.8,
         "自主创新 · 普通采购路径\n\n"
         "消歧改写 → ADP发现 → 断点①选人\n"
         "→ 并行初报 → 断点②议价?\n"
         "→ 断点③买法 → 共享标识下单\n"
         "→ 双边确认 → 放行询运 → 物流确认",
         fc="#ECFDF5", ec="#047857", fs=10)

    _box(ax, 7.3, 3.6, 6.4, 2.8,
         "自主创新 · 组群竞价路径\n\n"
         "冲突信号C1–C5建议 → 断点①是否组群\n"
         "→ 采购主持开群（供应）→ 群内出价\n"
         "→ 人决断下单对象 → 拉物流入群\n"
         "→ 系列工单多方确认",
         fc="#FFF7ED", ec="#C2410C", fs=10)

    _box(ax, 0.3, 0.4, 4.2, 2.8,
         "采购 AB 运行时\nWit/工具 · Case状态机\nAskUser+Gate\n主持组群",
         fc="#FDF2F8", ec="#BE185D", fs=10)
    _box(ax, 4.9, 0.4, 4.2, 2.8,
         "供应 ABC 运行时\n目录·库存·政策\n初报/议价智力\n工单确认",
         fc="#F0FDF4", ec="#15803D", fs=10)
    _box(ax, 9.5, 0.4, 4.2, 2.8,
         "物流运行时\n必填字段清单\n运力方案生成\n工单确认",
         fc="#F8FAFC", ec="#475569", fs=10)

    fig.tight_layout()
    path = OUT / "fig3-2_framework.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("WROTE", path)


def fig_seq_normal():
    fig, ax = plt.subplots(figsize=(15, 10), dpi=160)
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 11)
    ax.axis("off")
    ax.set_title("图3-3  普通采购路径时序（十点 · 三断点 · 双边确认）", fontsize=14, pad=12, fontweight="bold")

    actors = [("人", 1.2), ("采购", 4.0), ("梧桐", 6.8), ("供应", 9.6), ("物流", 12.6)]
    for name, x in actors:
        ax.text(x, 10.5, name, ha="center", fontsize=11, fontweight="bold")
        ax.plot([x, x], [0.4, 10.2], color="#CBD5E1", lw=1.2, ls="--")

    steps = [
        (9.7, "人", "采购", "「买300套脚轮」"),
        (9.1, "采购", "采购", "①改写→重型脚轮"),
        (8.5, "采购", "梧桐", "②ADP 发现"),
        (7.9, "梧桐", "采购", "n家+描述"),
        (7.3, "采购", "人", "③断点①多选确认"),
        (6.7, "人", "采购", "勾选供应"),
        (6.1, "采购", "供应", "④并行初报询价"),
        (5.5, "供应", "采购", "报价+规格"),
        (4.9, "采购", "人", "⑤断点②是否议价"),
        (4.3, "采购", "供应", "⑥议价/优惠（可选）"),
        (3.7, "采购", "人", "⑦断点③怎么买"),
        (3.1, "采购", "供应", "⑧下单+共享订单ID"),
        (2.5, "人/供应", "采购", "双边Gate确认→生效"),
        (1.9, "采购", "物流", "⑨放行后问必填清单"),
        (1.3, "采购", "供应", "⑩缺则补规格/交期"),
        (0.7, "采购", "物流", "下运单+双边确认"),
    ]
    xpos = {"人": 1.2, "采购": 4.0, "梧桐": 6.8, "供应": 9.6, "物流": 12.6, "人/供应": 1.2}
    for y, a, b, label in steps:
        x1, x2 = xpos[a], xpos[b]
        if a == b:
            ax.text(x1 + 0.15, y, label, fontsize=8, color="#0F172A",
                    bbox=dict(boxstyle="round,pad=0.2", fc="#FEF3C7", ec="#B45309", lw=0.8))
        else:
            ax.annotate("", xy=(x2, y), xytext=(x1, y),
                        arrowprops=dict(arrowstyle="->", color="#1D4ED8", lw=1.2))
            ax.text((x1 + x2) / 2, y + 0.12, label, ha="center", fontsize=7.5, color="#334155")

    fig.tight_layout()
    path = OUT / "fig3-3_seq_normal.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("WROTE", path)


def fig_seq_group():
    fig, ax = plt.subplots(figsize=(14, 8), dpi=160)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title("图3-4  组群竞价时序（采购主持 · 断点① · 货清后拉物流）", fontsize=14, pad=12, fontweight="bold")

    actors = [("人", 1.5), ("采购主持", 4.5), ("供应群", 8.0), ("物流", 11.5)]
    for name, x in actors:
        ax.text(x, 8.5, name, ha="center", fontsize=11, fontweight="bold")
        ax.plot([x, x], [0.5, 8.2], color="#CBD5E1", lw=1.2, ls="--")

    rows = [
        (7.6, "采购主持", "人", "C1–C5冲突 → 建议组群"),
        (6.8, "人", "采购主持", "断点①：确认组群+勾选成员"),
        (6.0, "采购主持", "供应群", "开群（仅供应）共同上下文"),
        (5.2, "供应群", "采购主持", "出价 / 优惠 / 对齐口径"),
        (4.4, "采购主持", "人", "整理选项 → 人决断下谁的单"),
        (3.6, "采购主持", "物流", "货意向清后邀请入群"),
        (2.8, "物流", "采购主持", "运力/线路/时间对齐"),
        (2.0, "采购主持", "供应群", "系列工单（货+运）"),
        (1.2, "人", "采购主持", "各方 Gate 确认完结"),
    ]
    xpos = {"人": 1.5, "采购主持": 4.5, "供应群": 8.0, "物流": 11.5}
    for y, a, b, label in rows:
        x1, x2 = xpos[a], xpos[b]
        ax.annotate("", xy=(x2, y), xytext=(x1, y),
                    arrowprops=dict(arrowstyle="->", color="#C2410C", lw=1.3))
        ax.text((x1 + x2) / 2, y + 0.15, label, ha="center", fontsize=8, color="#334155")

    fig.tight_layout()
    path = OUT / "fig3-4_seq_group.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("WROTE", path)


def fig_agent_runtime():
    fig, ax = plt.subplots(figsize=(14, 7), dpi=160)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("图3-5  单智能体运行时内部架构（全员同构智力底座）", fontsize=14, pad=12, fontweight="bold")

    _box(ax, 0.4, 5.2, 13.2, 1.3,
         "对话入口 / 控制台投影　　AskUser 挂起　　Gate 事件（确认/取消）",
         fc="#FCE7F3", ec="#BE185D", fs=10)
    _box(ax, 0.4, 3.5, 4.0, 1.4, "认知层\n意图理解·改写·建议\n(LLM + 系统提示)", fc="#E0E7FF", ec="#4338CA", fs=10)
    _box(ax, 4.6, 3.5, 4.4, 1.4, "工具网关\n只允许注册工具\n写库后强制重读快照", fc="#DCFCE7", ec="#166534", fs=10)
    _box(ax, 9.2, 3.5, 4.4, 1.4, "主数据\n目录/库存/政策/档案\n本角色权威数据", fc="#FEF3C7", ec="#B45309", fs=10)
    _box(ax, 0.4, 1.6, 6.4, 1.5, "协议适配\n/rpc · aip_start · ADP · AMP · 组群", fc="#EFF6FF", ec="#1D4ED8", fs=10)
    _box(ax, 7.2, 1.6, 6.4, 1.5, "工单与确认态\n共享订单标识 · buyer/supplier/logistics ack", fc="#FFF1F2", ec="#BE123C", fs=10)
    _box(ax, 0.4, 0.3, 13.2, 1.0,
         "铁律：对话只投影状态；Ask≠Gate；对端答不出规格/给不出方案 = 智力不合格",
         fc="#FEE2E2", ec="#991B1B", fs=10)

    fig.tight_layout()
    path = OUT / "fig3-5_agent_runtime.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("WROTE", path)


def fig_deploy():
    fig, ax = plt.subplots(figsize=(13, 6), dpi=160)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("图3-6  双云部署与六智能体分组", fontsize=14, pad=12, fontweight="bold")

    _box(ax, 0.4, 1.0, 5.8, 4.4,
         "腾讯云\n\n采购组：buyer-a :8010/:8090\n　　　　buyer-b :8012/:8092\n\n物流组：logistics :8015/:8095\n\nmTLS + 平台证书",
         fc="#DBEAFE", ec="#1D4ED8", fs=11)
    _box(ax, 6.8, 1.0, 5.8, 4.4,
         "阿里云\n\n供应组：supplier-a :8011/:8091\n　　　　supplier-b :8013/:8093\n　　　　supplier-c :8014/:8094\n\n同构智力运行时 + 分库",
         fc="#DCFCE7", ec="#166534", fs=11)
    _box(ax, 3.5, 0.15, 6.0, 0.7, "公网 AIP/ADP/AMP 连接 梧桐 wt.ioa.pub", fc="#FEF3C7", ec="#B45309", fs=10)

    fig.tight_layout()
    path = OUT / "fig3-6_deploy.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("WROTE", path)


if __name__ == "__main__":
    fig_architecture()
    fig_framework()
    fig_seq_normal()
    fig_seq_group()
    fig_agent_runtime()
    fig_deploy()
    print("ALL_DONE", OUT)
