# -*- coding: utf-8 -*-
"""第六、七章与参考文献（可写入最终完整版）。"""
from __future__ import annotations

from pathlib import Path

from _report_common import (
    IMG,
    SHOT,
    add_body,
    add_caption,
    add_heading,
    add_image,
    add_placeholder,
    add_table,
)

ROOT = Path(r"f:\code\智能体协议\项目开发\agentlink")


def write_chapter6(doc) -> None:
    add_heading(doc, "六、总结与展望", 1)

    add_heading(doc, "1. 经验总结", 2)
    add_body(
        doc,
        "采联 AgentLink 将「既有网络上的异构智能体互联」落到工业采销场景："
        "六智能体跨腾讯云/阿里云部署，经梧桐平台完成注册与发现，经 AIP 完成跨端互联，"
        "经 AMP Access/Message 形成可统计、可对账的访问过程证据，并在 HITL 门控下跑通"
        "普通询价与组群竞价两条业务闭环。回顾实施过程，可归纳如下经验与不足。",
    )

    add_heading(doc, "1.1 成功经验", 3)
    add_body(
        doc,
        "① 协议证据链优先于业务炫技。先保证 ACS/AIC 注册、ADP 平台发现、AIP 跨云 RPC、"
        "AMP 双侧落盘四条证据可核验，再叠加对话编排、比价/竞价与订单草案；评审材料与工程取证口径一致。"
        "② 容灾与缓存必须可解释。发现面「平台优先 + 显式 degrade/本地补齐标注」，禁止把本地候选伪装成平台命中；"
        "组群平面不可用时标注 transport=rpc 回退，业务面仍可闭环。"
        "③ HITL 守住高风险确认点。短名单确认、比价/下单等关键步骤需人工态门禁，reject 作废无脏询价。"
        "④ 访问过程双侧对账。Leader send 与 Partner receive 同 taskId / messageId=msg-{taskId} 写入 AMP，"
        "使「联了」可被审计；联调期 Access/Message 累计达数百次量级。"
        "⑤ 跨云真实部署暴露真问题。证书 CN 与 AIC 对齐、跨云 TLS 抖动、串行 invite 时延等，"
        "比单机多容器更能驱动工程硬化（并行 invite、早停、并行 RPC 等）。"
        "⑥ 二次开发边界清晰。国标报文结构不改，创新集中在编排、对账、HITL 与可解释容灾。",
    )

    add_heading(doc, "1.2 不足与改进点", 3)
    add_body(
        doc,
        "① 平台后台「智能体访问量」截图仍依赖人工与平台控制台能力，工程侧 AMP 不能替代该硬门槛材料。"
        "② 供应侧异构深度仍可加强：当前已含 Python graph 与 Java/LangChain4j Partner，"
        "更多运行时/目录差异与异常重协商策略有待扩展。"
        "③ 组群主路径需持续对抗 MQ/身份绑定波动；历史 E2E 已验证 transport=group，"
        "现场偶发回退虽可解释，但仍需提高组群平面稳定性。"
        "④ 取证自动化可再打包：一键导出「发现徽章 + AMP 配对 + 时延前后对照 + 材料清单」减少提交前手工拼装。"
        "⑤ 开源仓库已公开（https://github.com/ssa32883488-bot/agentlink）；"
        "梧桐技能分享截图等鼓励项材料可按实际进度继续补齐。",
    )

    add_heading(doc, "1.3 对本作品问题定义的再确认", 3)
    add_body(
        doc,
        "本作品验证的核心命题是：在保留各业务主体自主部署与异构实现的前提下，"
        "能否通过统一互联协议与平台能力，使采销智能体在既有网络上完成可发现、可互联、可访问取证的协同。"
        "联调与演示表明：协议面可稳定承载；业务面可在分钟级完成发现—询价—比价/竞价—草案；"
        "访问过程可被 AMP 连续记录。剩余缺口主要在平台后台截图类提交材料与组群平面稳态，而非协议可行性本身。",
    )

    add_heading(doc, "2. 未来规划", 2)
    add_body(
        doc,
        "后续工作按「标准化落地—功能深化—工程推广」三条线推进，时间上与赛后开源维护、工业场景试点相衔接。",
    )
    add_table(
        doc,
        ["方向", "近期（1–2 月）", "中期（一季度）", "预期产出"],
        [
            [
                "标准化落地",
                "后台访问量截图闭环；取证一键包",
                "材料模板与平台对接清单社区化",
                "可复用的提交材料包",
            ],
            [
                "功能拓展",
                "竞价策略与异常重协商；物流需求归一",
                "多品类 BOM/替代料；更多 Partner 运行时",
                "更完整的采销闭环样本",
            ],
            [
                "工程推广",
                "完善 README/部署文档；维护 GitHub 仓库",
                "梧桐技能/工具分享；社区 Issue 反馈",
                "可被复用的工业互联样例",
            ],
            [
                "性能与稳态",
                "组群 MQ 稳态与演练脚本",
                "跨云容灾演练自动化、SLA 看板",
                "可解释的高可用路径",
            ],
        ],
        "表6-1　未来规划路线图",
    )
    add_image(doc, IMG / "ch6-v2-roadmap.png", "图6-1　总结与展望路线示意")
    add_image(doc, IMG / "ch4-v2-dual-cloud.png", "图6-2　跨云部署拓扑（后续推广仍以此为基线）")
    add_body(
        doc,
        "长远看，希望「采联」成为 AIP/ACPs 生态中可对照的工业采销互联样本："
        "后来者可按登记表完成入驻，按门户名单部署，按双路径脚本取证，按 AMP 口径证明访问过程，"
        "再按自身行业规则扩展业务编排——协议面稳定，业务面可创新。",
    )


def write_chapter7(doc) -> None:
    add_heading(doc, "七、附录", 1)
    add_body(
        doc,
        "本章汇集提交与复现所需的支撑材料索引。正文已论证的技术点此处不重复展开；"
        "红色占位项须在提交前由人工替换为真实截图或公开链接。参考文献单列于附录之后。",
        first_indent=True,
    )

    # ----- 体验地址（置前便于评审试用） -----
    add_heading(doc, "附录〇　项目体验地址（六智能体控制台）", 2)
    add_body(
        doc,
        "以下为采联 AgentLink 公网可访问的六智能体独立控制台入口，可用于评审体验与复现演示。"
        "采购侧（腾讯云）建议从采购商A进入，发送「启动正式采购 / 发现供应商」走普通询价，"
        "或按界面提示进入组群竞价；供应侧与物流侧可观察协作面板、询价箱与工单状态。"
        "浏览器若提示证书告警，属自签/跨云演示环境，按指引继续访问即可。"
        "开源仓库：https://github.com/ssa32883488-bot/agentlink 。",
    )
    add_table(
        doc,
        ["智能体", "角色", "体验地址（控制台）", "协议 API"],
        [
            [
                "采购商A",
                "Leader",
                "https://ashui.online:8090/",
                "https://ashui.online:8010",
            ],
            [
                "采购商B",
                "Leader",
                "https://ashui.online:8092/",
                "https://ashui.online:8012",
            ],
            [
                "物流",
                "Partner",
                "https://ashui.online:8095/",
                "https://ashui.online:8015",
            ],
            [
                "供应商A",
                "Partner",
                "http://39.105.20.113:8091/",
                "https://39.105.20.113:8011",
            ],
            [
                "供应商B",
                "Partner",
                "http://39.105.20.113:8093/",
                "https://39.105.20.113:8013",
            ],
            [
                "供应商C",
                "Partner",
                "http://39.105.20.113:8094/",
                "https://39.105.20.113:8014",
            ],
        ],
        "表〇-1　项目体验地址一览",
    )
    add_body(
        doc,
        "建议体验路径：① 打开采购商A控制台 → 智能对话发起采购；② 确认平台发现短名单（HITL）；"
        "③ 并行询价后查看比价/下单或转入组群竞价；④ 同步打开供应A/B/C 与物流控制台观察回执与协作状态。"
        "健康检查可对上述 API 根路径访问 /health（若已暴露）。",
        first_indent=True,
    )

    # ----- A -----
    add_heading(doc, "附录A　平台 AIC 登记表（六智能体）", 2)
    add_body(
        doc,
        "下表与线上证书 CN / 运行时环境变量对齐（更新于 2026-10），用于核验「注册」项。"
        "详细说明见工程文档 docs/平台AIC登记表.md、docs/aic码.md。",
    )
    add_table(
        doc,
        ["名称", "id", "AIC（节选末段）", "RPC endPoint", "部署"],
        [
            ["采联采购智能体A", "buyer-a", "…MWEDJS.0GUC", "https://ashui.online:8010/rpc", "腾讯云"],
            ["采联采购智能体B", "buyer-b", "…DR2I98.0IWJ", "https://ashui.online:8012/rpc", "腾讯云"],
            ["采联物流智能体", "logistics", "…39B1TM.0ALR", "https://ashui.online:8015/rpc", "腾讯云"],
            ["采联供应商智能体A", "supplier-a", "…AE0C7A.1CHP", "https://39.105.20.113:8011/rpc", "阿里云"],
            ["采联供应商智能体B", "supplier-b", "…2UXYPG.1CQG", "https://39.105.20.113:8013/rpc", "阿里云"],
            ["采联供应商智能体C", "supplier-c", "…SY0GFP.09NH", "https://39.105.20.113:8014/rpc", "阿里云"],
        ],
        "表A-1　六智能体 AIC / 端点登记摘要",
    )
    add_body(
        doc,
        "完整 AIC 字符串以平台回填与证书 CN 为准；环境变量片段见 config/platform_aics.env。"
        "若 CN 与运行时 AIC 不一致，会出现 SenderIdentityMismatch / AuthorizationFailed，属身份绑定硬约束。",
    )

    # ----- B -----
    add_heading(doc, "附录B　控制台门户与双云部署", 2)
    add_body(
        doc,
        "每个智能体独立控制台、独立进程、独立业务库；智能体之间仅通过 ADP 发现与 AIP 任务协作。"
        "名单见 docs/agent_portals.md。",
    )
    add_table(
        doc,
        ["智能体", "角色", "API", "控制台 UI"],
        [
            ["采购商A", "Leader", "https://ashui.online:8010", "https://ashui.online:8090/"],
            ["采购商B", "Leader", "https://ashui.online:8012", "https://ashui.online:8092/"],
            ["物流", "Partner", "https://ashui.online:8015", "https://ashui.online:8095/"],
            ["供应商A", "Partner", "https://39.105.20.113:8011", "http://39.105.20.113:8091/"],
            ["供应商B", "Partner", "https://39.105.20.113:8013", "http://39.105.20.113:8093/"],
            ["供应商C", "Partner", "https://39.105.20.113:8014", "http://39.105.20.113:8094/"],
        ],
        "表B-1　六智能体 API 与控制台入口",
    )
    add_table(
        doc,
        ["云", "主机", "承载"],
        [
            ["腾讯云", "ashui.online / 81.70.46.119", "采购A/B、物流及其 UI"],
            ["阿里云", "39.105.20.113", "供应商A/B/C（AIP HTTPS）+ 控制台 UI"],
        ],
        "表B-2　双云部署主机",
    )
    add_image(doc, SHOT / "wutong_portal_public.png", "图B-1　梧桐门户公开页（wt.ioa.pub）")
    add_image(doc, SHOT / "ui_buyer-a_chat_turn2.png", "图B-2　采购商A控制台实拍（发现/HITL，附录留存）")

    # ----- C -----
    add_heading(doc, "附录C　协议/梧桐交互测试数据摘要", 2)
    add_body(
        doc,
        "全量整理见 docs/evidence/chapter5_run/INTERACTION_FULL_INVENTORY.md；"
        "远程落盘件见 remote_amp_20261030/；连续窗口见 metrics_snapshot.json。"
        "下表为提交材料用的概括口径（与第五章一致）。",
    )
    add_table(
        doc,
        ["指标", "数值", "说明"],
        [
            ["观测窗口", "2026-10-25～10-30", "联调+演示密集期"],
            ["AMP Access 累计", "约 349 次", "窗口 155 + 10/30 当日 194"],
            ["AMP Message 累计", "约 328 次", "窗口 134 + 10/30 当日 194"],
            ["唯一 taskId（窗口）", "151", "metrics_snapshot"],
            ["协议任务成功率", "91.0%", "终态成功/可确认"],
            ["AMP HTTP 成功率", "99.49%", "Access statusCode 2xx"],
            ["Message 投递成功率", "100%", "远程 jsonl 无 error"],
            ["业务报价准确率", "95.2%", "有效报价字段抽样"],
            ["平台 ADP 命中准确率", "93.8%", "source=platform_adp"],
            ["竞拍墙钟（优化后）", "≈7.6 s", "相对 30–120s+，约 4–15×"],
            ["RPC 并行盲拍", "≈311 ms", "latency_opt 实测"],
        ],
        "表C-1　交互与时延代表性指标",
    )
    add_body(
        doc,
        "代表性案例：普通询价 case-e96ee172；组群竞价现场 case-fba29488；"
        "历史组群 E2E（transport=group + TCO）见 docs/evidence/group_e2e_case_smoke.md；"
        "时延前后对照见 docs/evidence/latency_opt/BEFORE_AFTER.md。",
    )
    add_placeholder(doc, "【待补】梧桐平台后台 · 智能体访问量截图（附录C硬门槛，与第五章图5-7同槽）")
    add_caption(doc, "图C-1　平台后台访问量截图（占位）")

    # ----- D -----
    add_heading(doc, "附录D　演示视频分镜说明（3–5 分钟）", 2)
    add_body(
        doc,
        "演示视频用于佐证「注册—发现—互联—访问」与业务闭环。录制禁止出镜校名/LOGO/指导教师；"
        "画质优先特写协议证据。完整脚本见 docs/materials/演示视频分镜脚本_3to5min.md。",
    )
    add_table(
        doc,
        ["段", "时长", "画面要点", "旁白要点"],
        [
            ["片头", "10s", "作品名「采联 AgentLink」", "基于 AIP 与梧桐平台"],
            ["拓扑", "25s", "腾讯采购侧 / 阿里供应侧", "六智能体、mTLS、协议平面"],
            ["注册", "30s", "ACS/AIC 或六端点健康检查", "已完成平台注册"],
            ["ADP 发现", "45s", "平台徽章；必要时 refresh", "真平台发现，非本地伪造"],
            ["AIP 询价", "50s", "三家并行；协作时间线", "跨云 AIP RPC"],
            ["AMP 配对", "50s", "同 taskId；或后台访问量", "Access 双侧匹配计次"],
            ["HITL", "30s", "确认或一次 reject", "高风险人机门禁"],
            ["收束", "20s", "KPI + 开源价值", "必要验证已跑通"],
        ],
        "表D-1　演示视频分镜摘要",
    )
    add_body(
        doc,
        "录制前建议在 buyer 主机执行：python scripts/demo_acps_evidence.py，"
        "期望 ACPS_EVIDENCE_PASS 并生成 docs/evidence/latest_pair.json。"
        "若发现走容灾路径，旁白须明示「本地 ACS 容灾补齐」，并另录一条纯平台命中镜头。",
    )
    add_placeholder(doc, "【待补】演示视频文件或网盘链接（MP4，3–5 分钟）")
    add_caption(doc, "材料D-1　演示视频占位")

    # ----- E -----
    add_heading(doc, "附录E　工程源码与脚本索引", 2)
    add_body(
        doc,
        "本作品在 AIP/ACPs 开源栈上二次开发。本地可按 README 启动全量六智能体；"
        "线上以 /opt/agentlink 为准。下表列出与取证、部署强相关的路径（完整树见仓库）。",
    )
    add_table(
        doc,
        ["路径", "用途"],
        [
            ["commerce_v2/ / commerce/", "业务编排、发现、RFQ、竞价、AMP 埋点"],
            ["acs/*.acs.json", "平台入驻 ACS 描述"],
            ["config/platform_aics.env", "AIC 环境变量片段"],
            ["scripts/start_all_local.ps1", "本地六体启动"],
            ["scripts/smoke_all_local.py", "本地全量协议冒烟"],
            ["scripts/demo_acps_evidence.py", "比赛证据一键（期望 ACPS_EVIDENCE_PASS）"],
            ["scripts/chapter5_dual_path_evidence.py", "普通询价/组群竞价 API 取证"],
            ["scripts/chapter5_ui_chat_screenshots.py", "六体控制台浏览器截图"],
            ["scripts/_inventory_ch5_interactions.py", "AMP 交互全量汇总"],
            ["scripts/_deploy_latency_opt.py", "竞拍时延优化部署"],
            ["docs/evidence/chapter5_run/", "第五章证据与交互库存"],
            ["docs/evidence/latency_opt/", "时延前后对照与 bench"],
        ],
        "表E-1　关键源码与脚本索引",
    )
    add_body(
        doc,
        "开源改造要点（相对标准 demo）：① 双侧 AMP 同 taskId 对账；② 对话驱动 + HITL 四态门禁；"
        "③ ADP 平台优先且容灾可解释；④ 跨云双部署与证书/AIC 对齐；⑤ 竞拍路径并行化与早停。"
        "带注释代码包随仓库提交；部署说明见 README 与 docs/注册提交材料清单.md（如有）。",
    )

    # ----- F -----
    add_heading(doc, "附录F　开源贡献与其他佐证（鼓励项）", 2)
    add_body(
        doc,
        "本作品工程代码已开源：https://github.com/ssa32883488-bot/agentlink 。"
        "鼓励在梧桐科研平台分享智能体、技能与工具；鼓励向 AtomGit / GitHub 的 AIP-PUB 生态提交代码与 Issue。"
        "下列材料中，仓库链接已落实；截图类按实际上线进度补齐。",
    )
    add_table(
        doc,
        ["材料", "状态", "说明"],
        [
            [
                "公开 GitHub 仓库",
                "已公开",
                "https://github.com/ssa32883488-bot/agentlink",
            ],
            ["README / 关键 Commit 截图", "建议补", "证明二次开发与持续提交"],
            ["Issue / 技术笔记", "可选", "反馈 ACPs/平台对接经验"],
            ["梧桐平台技能/工具分享截图", "待补", "鼓励项"],
            ["试点/应用证明、软著专利", "如有则附", "不虚构"],
        ],
        "表F-1　开源与其他佐证清单",
    )
    add_body(
        doc,
        "开源仓库地址：https://github.com/ssa32883488-bot/agentlink "
        "（采联 AgentLink 异构采销多智能体互联协同系统）。",
        first_indent=False,
    )
    add_caption(doc, "材料F-1　开源仓库地址")
    add_placeholder(doc, "【待补截图】梧桐科研平台 · 技能/工具分享页")
    add_caption(doc, "图F-1　平台分享截图（占位）")

    # ----- G -----
    add_heading(doc, "附录G　必要验证材料总清单", 2)
    add_table(
        doc,
        ["验证项", "工程侧证据", "提交材料"],
        [
            ["注册", "六体 ACS 提交 + AIC 回填；附录A", "平台列表/登记截图（建议补）"],
            ["发现", "source=platform_adp 证据 JSON；第五章图", "平台发现命中控制台截图（待补）"],
            ["互联", "跨云 AIP RFQ；组群/RPC 回退闭环", "协作时间线/视频特写"],
            ["访问", "AMP Access/Message 全量整理；附录C", "后台访问量截图（硬门槛，待补）"],
        ],
        "表G-1　必要验证对照总表",
    )
    add_body(
        doc,
        "结论：工程侧四项均已具备可核验证据；提交阻断项为平台后台访问量截图及建议补齐的发现命中/"
        "在线状态截图。附录其余清单用于复现、演示与开源鼓励项。",
    )


def write_references(doc) -> None:
    add_heading(doc, "参考文献", 1)
    refs = [
        "[1] 新华社.《人工智能 智能体互联》系列7项国家标准发布[EB/OL]. 中国政府网, 2026-06-26.",
        "[2] ISG. State of the Agentic AI Market Report[R]. 2025.",
        "[3] Chen W, et al. Internet of Agents[J/OL]. arXiv:2407.07061, 2024.",
        "[4] ABI Research. Can A2A and MCP … Solve … Multi-Agent Systems?[R/OL]. 2025.",
        "[5] Futurum Research. Agentic AI Open Standards Report: 1H-2025[R]. 2025.",
        "[6] Gartner. Innovation Insight: AI Agent Communication Protocols[R]. 2025.",
        "[7] 开放原子开源基金会. AIP开源项目在AtomGit正式开源[EB/OL]. 2026-07-07.",
        "[8] Ehtesham A, et al. A survey of agent interoperability protocols[J/OL]. arXiv:2505.02279, 2025.",
        "[9] Collaborative Agentic AI Needs Interoperability Across Ecosystems[J/OL]. arXiv:2505.21550, 2025.",
        "[10] Liu J, Yu K, Chen K, et al. ACPs: Agent Collaboration Protocols for the Internet of Agents[J/OL]. arXiv:2505.13523, 2025. https://doi.org/10.48550/arXiv.2505.13523",
        "[11] 刘军, 于珂, 陈克亮, 等. ACPs：面向智能体互联网的智能体协作协议体系[EB/OL]. 2025.",
        "[12] Liu J, Yu K, Li K, et al. Agent Collaboration Protocols Architecture for Internet of Agents[EB/OL]. IETF Internet-Draft draft-liu-dmsc-acps-arc, 2026.",
        "[13] GB/Z 185.1—2026～185.7—2026 人工智能 智能体互联[S]. 2026.",
        "[14] 全国信标委. 智能体互联系列国家标准解读[EB/OL]. 2026.",
        "[15] 开放原子开源基金会 / AIP-PUB. AIP 开源与 ACPs 参考实现相关说明[EB/OL]. AtomGit/GitHub, 2026.",
        "[16] 梧桐智能体科研平台. 平台手册与接入指引[EB/OL]. https://wt.ioa.pub/",
        "[17] 采联 AgentLink 工程文档. docs/agent_portals.md、平台AIC登记表、交互全量整理等[Z]. 2026.",
        "[18] 梧桐平台. 注册/发现/互联/访问验证说明[EB/OL]. 2026.",
        "[19] Berners-Lee T, et al. 万维网演进相关论述与回顾[EB/OL].",
        "[20] 业界关于 Web 1.0/2.0/3.0 的阶段性归纳（分析框架引用）[Z].",
        "[21] Berners-Lee T. 关于软件代理分担流程、人专注决策的相关展望[EB/OL].",
        "[22] Akerlof G A. The Market for “Lemons”: Quality Uncertainty and the Market Mechanism[J]. Quarterly Journal of Economics, 1970, 84(3): 488-500.",
        "[23] Özer Ö, Raz G. Supply Chain Sourcing Under Asymmetric Information[J]. Production and Operations Management, 2011, 20(1): 92-115.",
        "[24] Niskanen T, et al. Modern mediators: intermediaries’ informational roles in sourcing from China[J/OL]. Journal of Business & Industrial Marketing.",
        "[25] Internetization, supplier search, and diversification of global supply chains[J]. European Economic Review, 2025, 172. DOI:10.1016/j.euroecorev.2025.104929.",
        "[26] Barua A, et al. Efficient Selection of Suppliers over the Internet[J]. Journal of Management Information Systems, 1997, 13(4): 117-137.",
        "[27] Chamodrakas I, Batis D, Martakos D. Supplier selection in electronic marketplaces using satisficing and fuzzy AHP[J]. Expert Systems with Applications, 2010, 37(1): 490-498.",
        "[28] A governed framework combining large language models and human oversight for supplier selection[J]. Machine Learning with Applications, 2026. DOI:10.1016/j.mlwa.2026.101028.",
        "[29] 爱分析. 2026爱分析·装备制造行业供应链智能体研究报告[R]. 2026.",
        "[30] Ivalua / Proconomy 等. Agentic / Governed Autonomous Procurement：人工检查点与授权治理实践[EB/OL]. 2025-2026.",
        "[31] Supplier Selection Criteria under Heterogeneous Information Disclosure / Information Overload in B2B Platforms[R/OL].",
    ]
    for ref in refs:
        add_body(doc, ref, first_indent=False)
