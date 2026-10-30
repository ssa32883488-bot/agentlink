# -*- coding: utf-8 -*-
"""Build complete AIC technical report DOCX from project facts + generated figures."""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

IMG = Path(r"f:\code\智能体协议\outputs\custom-imagegen")
OUT = Path(r"C:\Users\32081\Desktop\智能体互联技术报告_完整版.docx")
OUT2 = Path(r"f:\code\智能体协议\项目开发\agentlink\docs\materials\智能体互联技术报告_完整版.docx")


def set_run_font(run, *, east="宋体", ascii_font="Times New Roman", size=12, bold=False):
    run.font.name = ascii_font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east)
    run.font.size = Pt(size)
    run.bold = bold


def add_heading(doc, text, level=1):
    p = doc.add_paragraph()
    run = p.add_run(text)
    if level == 1:
        set_run_font(run, east="黑体", size=16, bold=True)
    elif level == 2:
        set_run_font(run, east="黑体", size=14, bold=True)
    else:
        set_run_font(run, east="楷体", size=12, bold=True)
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    return p


def add_body(doc, text, *, first_indent=True):
    p = doc.add_paragraph()
    # support [n] superscript-ish by keeping plain brackets (Word true superscript optional)
    run = p.add_run(text)
    set_run_font(run, size=12)
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.space_after = Pt(6)
    if first_indent:
        pf.first_line_indent = Cm(0.74)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def add_caption(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=10.5, bold=True)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.first_line_indent = Cm(0)


def add_image(doc, path: Path, caption: str, width_cm=15.5):
    if not path.exists():
        add_body(doc, f"【插图缺失：{path.name}】", first_indent=False)
        add_caption(doc, caption)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Cm(0)
    run = p.add_run()
    run.add_picture(str(path), width=Cm(width_cm))
    add_caption(doc, caption)


def add_table(doc, headers, rows, caption=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        r = cell.paragraphs[0].add_run(h)
        set_run_font(r, east="黑体", size=10.5, bold=True)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = ""
            r = cell.paragraphs[0].add_run(str(val))
            set_run_font(r, size=10.5)
    if caption:
        add_caption(doc, caption)
    doc.add_paragraph()


def build():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.5)
    sec.right_margin = Cm(2.5)
    sec.top_margin = Cm(2.5)
    sec.bottom_margin = Cm(2.5)

    # Title
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("AIC·智能体互联技术方案")
    set_run_font(r, east="黑体", size=18, bold=True)
    st = doc.add_paragraph()
    st.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = st.add_run("作品名称：采联 AgentLink —— 异构采销多智能体互联协同系统")
    set_run_font(r2, east="宋体", size=12)
    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rn = note.add_run("（全文不出现参赛单位校名、LOGO与指导教师信息）")
    set_run_font(rn, size=10.5)
    rn.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # ========== 一 ==========
    add_heading(doc, "一、作品概述", 1)
    add_heading(doc, "1. 行业与技术背景", 2)
    add_body(
        doc,
        "人工智能正从感知理解迈向生成决策与自主执行，智能体已成为赋能千行百业的重要载体[1]。产业对多智能体投入上升，但已部署方案中真正采用多智能体形态的比例仍偏低[2]，说明「单点智能」与「跨主体协同」之间仍有落差。",
    )
    add_body(
        doc,
        "借用业界常用的 Web 1.0/2.0/3.0 分析框架[19][20]：Web 1.0 侧重人从网络单向获取信息；Web 2.0 转向用户参与、平台连接与信息大规模生产。信息量随之激增，而人的处理能力并未同步提升，甄别、沟通与决策负担加重。大模型在数据、算法与算力等多因素推动下提升了信息处理能力；当其接入工具与业务系统后，Agent 开始替人完成整理需求、信息初筛与信息积累等任务。但不同主体各自部署 Agent 后，若缺少统一发现与互信交互机制，仍无法跨系统协作——智能体互联正是补齐这一环的关键方向（见图1）。Berners-Lee 亦曾展望由软件代理分担流程繁琐、人专注决策与创意[21]；对本作品而言，重点不在重定义「互联网3.0」，而在探索不同业务主体如何在保留自主性的同时，通过共同协议实现 Agent 协作。",
    )
    add_image(doc, IMG / "fig1-web-evolution.png", "图1　从Web演进到智能体互联（分析框架示意）")

    add_table(
        doc,
        ["阶段", "核心能力", "典型任务（以采销为例）"],
        [
            ["Web 1.0", "人获取信息", "检索供应商"],
            ["Web 2.0", "人发布、联系、交易", "发需求、比报价"],
            ["AI应用", "AI理解信息并调用工具", "整理需求、生成询价"],
            ["智能体互联", "跨主体Agent协作", "发现、询价、协商、推进订单"],
        ],
        "表1　能力递进对照",
    )

    add_heading(doc, "（1）异构互通与协同落地痛点", 3)
    add_body(
        doc,
        "异构智能体在身份、能力描述、发现、交互与工具调用上缺乏统一规范，适配成本高、协同效率低、可信管理难[7]；MCP、A2A、ANP 等国际协议各有侧重，生态仍碎片化[8][9][4-6]。落地层面突出表现为：协议异构使人充当桥接；身份与权限难统一导致关键业务不敢跨主体委托；多轮协商与工具调用使 Demo 易、生产难[2]。采销网络中信息差长期存在，平台曝光又推高甄别、沟通、信任与决策成本；各方即便有 AI，技术栈与接口不通则仍无法直连——亟需可互信、可发现、可协作的互联底座（见图2）。",
    )
    add_image(doc, IMG / "fig2-hetero-pain.png", "图2　异构智能体协同落地痛点示意")

    add_heading(doc, "（2）国家标准 AIP 与 ACPs 开源底座", 3)
    add_body(
        doc,
        "我国已发布 GB/Z 185—2026《人工智能 智能体互联》系列标准，覆盖身份、描述、发现、交互与工具调用等闭环[13][14][1]。北邮刘军等提出的 ACPs 协议族面向智能体互联网的注册、发现、交互与工具调用，并指出既有协议偏场景化、难单独支撑规模化互联[10][11]。公开说明进一步明确：AIP 国标以 ACPs 为重要共识基础，ACPs 代码为 AIP 开源社区首套参考实现[15][7]；梧桐平台据此提供注册、发现、互联与访问验证[18]。标准与开源已具备可接入条件，关键转向真实异构业务的协同实证（见图3、图4）。",
    )
    add_image(doc, IMG / "fig3-aip-acps.png", "图3　国家标准AIP与ACPs开源底座")
    add_image(doc, IMG / "fig4-necessity.png", "图4　本作品问题—标准—目标逻辑链")

    add_heading(doc, "（3）本作品的必要性与意义", 3)
    add_body(
        doc,
        "综上，智能体互联已进入「标准确立、开源可用、平台可验」窗口，但仍缺场景化验证。本作品以 AIP 国标及 ACPs 开源实现为基线，面向采销异构多智能体场景，验证发现、互信互联与协同交互：技术上落实国标闭环的工程可落地性；实践上分担信息甄别与初步沟通等成本，并完成梧桐全流程验证。一句话：协议解决「怎么通」，本作品回答「通了之后如何协同增效」。",
    )

    add_heading(doc, "2. 作品目标定位", 2)
    add_body(
        doc,
        "本作品定名为「采联 AgentLink」，核心研发目标是：基于 AIP 智能体互联开源参考实现（ACPs），遵循 GB/Z 185 系列国家标准，搭建面向工业采销场景的异构多智能体互联协同系统，使采购、供应、物流等业务智能体在统一协议平面上完成自动发现、跨端互联与可验证访问，并形成可演示、可部署的业务闭环。目标定位可概括为「目标三角」：硬性合规、业务场景、技术与效益（见图5）。",
    )
    add_image(doc, IMG / "sec12-goals-triangle.png", "图5　作品目标定位三角")

    add_heading(doc, "（1）硬性目标与梧桐全流程验证要求", 3)
    add_body(
        doc,
        "依据赛题必要验证场景，本作品硬性目标明确如下：成功接入梧桐智能体互联平台（https://wt.ioa.pub/），实现智能体自动发现与跨端访问；并在梧桐智能体科研平台完成注册、发现、互联、访问全流程验证，留存可核查的验证记录。",
    )
    add_table(
        doc,
        ["验证环节", "目标要求", "本作品对应能力（现状）"],
        [
            ["注册", "AIC/ACS 平台身份注册", "六智能体 ACS 已提交，AIC 已审核回填并绑定公网端点"],
            ["发现", "ADP 自动发现", "采购侧经平台 Discovery 发现供应候选，可强制刷新"],
            ["互联", "AIP 跨端调用", "跨云 HTTPS RPC 询价/回执；支持组群消息协同"],
            ["访问", "AMP 访问留痕 + 后台数据", "双侧 Access/Message 上报与同任务对账已具备；平台后台访问量截图仍为提交硬门槛（官方暂无查询接口）"],
        ],
        "表2　梧桐必要验证场景与本作品对应关系",
    )
    add_image(doc, IMG / "sec12-wutong-four-steps.png", "图6　梧桐平台必要验证全流程")

    add_heading(doc, "（2）业务场景与协同功能", 3)
    add_body(
        doc,
        "落地场景为座椅零部件采销业务网络：采购方提出物料需求，多家供应方差异化报价，物流方提供运费与时效，最终形成可确认的订单草案。系统部署六枚业务智能体，采购/物流与供应分属不同云主机，统一经 AIP/ACPs 互通，以验证「主体不同、数据不同、仍可协作」（见图7）。",
    )
    add_table(
        doc,
        ["智能体", "业务角色", "协同职责（摘要）"],
        [
            ["采购A/B", "买方 Leader", "需求理解、平台发现、HITL短名单、并行询价、比价与路径选择、订单草案"],
            ["供应A/B/C", "卖方 Partner", "差异化报价与促销、可选合入运费、议价/组群竞价响应"],
            ["物流", "运力 Partner", "运费/时效估算，支撑货运捆包与TCO比较"],
        ],
        "表3　六智能体角色与协同职责",
    )
    add_image(doc, IMG / "sec12-six-agents.png", "图7　采销六智能体协同拓扑")
    add_body(
        doc,
        "可实现的协同功能：① 平台侧自动发现；② HITL 短名单确认；③ 多家并行询价与比价；④ 促销/门槛类议价方案推演；⑤ 可选组群竞价与 TCO 选商；⑥ 物流合入后综合成本比较；⑦ 双边确认与订单激活；⑧ 协议平面访问留痕与任务级对账。",
    )

    add_heading(doc, "（3）预期技术指标与效益", 3)
    add_table(
        doc,
        ["类别", "预期/已实现指标"],
        [
            ["功能", "六体完成注册/发现/互联/访问链路；主路径「发现→询价→比价→确认」可跑通；HITL四态可用"],
            ["性能", "支持对不少于3家供应方并行询价；发现与调用时延可记录；组群协同冒烟通过"],
            ["兼容", "不改国标ACS/AIC/ADP/AIP/AMP报文结构；跨云HTTPS RPC"],
            ["可部署", "双云可部署；脚本化启动与联调取证；AIC配置可追溯"],
        ],
        "表4　技术指标",
    )
    add_body(
        doc,
        "技术效益：形成「国标协议面不变、业务与编排可创新」的二次开发范式。社会效益：面向采销信息差与高沟通成本，用智能体协同分担检索、初筛、询价与比价。开源鼓励项：基于 AIP-PUB 生态开发，计划在 AtomGit/GitHub AIP-PUB 进行开源与反馈，并鼓励在梧桐平台分享智能体/技能/工具模块。",
    )

    # ========== 二 ==========
    add_heading(doc, "二、需求分析", 1)
    add_heading(doc, "1. 行业痛点剖析", 2)
    add_body(
        doc,
        "结合梧桐接入与开源落地实践，本作品需解决的关键问题包括：① 异构主体如何在统一身份与能力描述下被发现；② 跨云环境下如何完成安全的任务级互联调用；③ 如何在不改国标报文的前提下承载真实采销业务；④ 如何让「访问」可对账、可留痕，避免「联了但不可证」。痛点与赛题硬门槛直接对齐：注册、发现、互联、访问四步缺一不可。",
    )
    add_heading(doc, "2. 场景与功能需求", 2)
    add_body(
        doc,
        "目标场景为工业座椅供应链采销协同。功能上需要对话驱动的采购编排、平台优先的发现、并行询价、人机协同确认、促销方案推演、可选组群竞价、物流合入与订单激活。非功能上要求跨云可部署、协议兼容、过程可观测。",
    )
    add_table(
        doc,
        ["需求类别", "具体指标"],
        [
            ["功能", "ADP发现、AIP询价/议价/竞价/物流、HITL四态、对话编排、AMP双侧留痕"],
            ["性能", "并行≥3家询价；发现可refresh强制打平台；关键链路可在演示窗口内完成"],
            ["兼容性", "ACS/AIC/ADP/AIP/AMP报文不改国标结构；跨云HTTPS端点"],
            ["可部署", "双云进程可拉起；一键/脚本化冒烟与证据采集"],
        ],
        "表5　功能/性能/兼容/可部署需求指标",
    )

    # ========== 三 ==========
    add_heading(doc, "三、智能体互联技术选型与方案设计", 1)
    add_heading(doc, "1. 基础开发资源选型", 2)
    add_body(
        doc,
        "本作品遵循 AIP 国标思路，以开放原子 AIP-PUB / ACPs 开源实现为协议基座，对接梧桐 Registry、CA、Discovery 与消息/Kafka 访问通道。业务运行时采用 Python 3.12 + FastAPI；采购对话编排采用 Wit Framework + DeepSeek（OpenAI 兼容）；Partner 侧采用确定性业务图（graph）保证报价可复现；数据层以 SQLite 支撑演示级 ERP/库存。开发与联调环境覆盖双云公网 HTTPS 端点。",
    )
    add_heading(doc, "2. 核心技术方案设计", 2)
    add_body(
        doc,
        "整体采用「业务对话与 HITL → 采购编排 → 协议平面 → 双云部署」分层架构（见图8）。协议平面统一承载 AIC/ACS/ADP/AIP/AMP：采购作为 Leader 发起发现与任务，供应与物流作为 Partner 通过 /rpc 响应；访问在 Leader send 与 Partner receive 双侧记录，并上报 Kafka，实现同 taskId / messageId 对账。",
    )
    add_image(doc, IMG / "ch3-architecture.png", "图8　采联AgentLink总体架构")
    add_body(
        doc,
        "关键技术选型：① 注册发现——ACS 描述能力，AIC 标识身份，ADP 走平台 Discovery；② 跨体数据传输——AIP 结构化任务与回执；③ 协同调度——采购案状态机 + 并行 RFQ + 议价/组群双路径；④ 安全交互——平台证书体系与可选身份绑定，组群平面可独立配置绑定策略。",
    )
    add_image(doc, IMG / "ch3-reuse-innovate.png", "图9　开源复用与自主创新边界")
    add_body(
        doc,
        "开源复用与自主创新边界（见图9）：复用 ACPs/AIP SDK、身份注册发现交互访问报文及梧桐接入能力；自主创新集中在采销六体业务编排、HITL 门禁、促销方案推演（scheme_planner）、组群竞价与 TCO 选商、双侧 AMP 对账及跨云部署运维。原则是「国标报文结构不改，业务与证据链可深化」。",
    )

    # ========== 四 ==========
    add_heading(doc, "四、项目实施", 1)
    add_heading(doc, "1. 整体实施方案", 2)
    add_body(
        doc,
        "实施流程为：需求拆解 → 开源代码适配改造 → AIP 标准兼容开发 → 梧桐平台对接调试 → 双云联调与证据采集 → 材料整理。团队按协议平面、采购编排、供应/物流 Partner、UI 与取证脚本分工协作。资源配置上，采购/物流部署于腾讯云主机，供应部署于阿里云主机，统一接入梧桐平台服务。",
    )
    add_heading(doc, "2. 关键技术落地实现", 2)
    add_body(
        doc,
        "（1）开源二次开发：在 acps-sdk 之上封装发现缓存、强制 refresh、容灾显式标注（禁止把本地补齐伪装成平台命中）；在业务层实现采购案状态机与工具网关。（2）AIP 适配：Leader 通过结构化 AIP 发起询价等任务，Partner 以确定性 graph 产出可审计回执。（3）梧桐接入：六体完成 ACS 提交与 AIC 回填；Discovery 采用平台路径；AMP 写入 access/message 主题。（4）业务创新：HITL 四态（approve/edit/reject/respond）；scheme_planner 多方案推演；组群竞价与 TCO 选商。主路径见图10。",
    )
    add_image(doc, IMG / "ch4-procurement-seq.png", "图10　采购协同主路径")
    add_body(
        doc,
        "兼容性问题上，跨云证书、发现时延与身份绑定策略曾是主要瓶颈。对策包括：公网 HTTPS 端点统一、发现可 refresh、本地默认弱绑定以便联调、组群平面独立绑定配置，以及双侧 AMP 对账保证访问证据闭环。",
    )

    # ========== 五 ==========
    add_heading(doc, "五、应用成效", 1)
    add_heading(doc, "1. 功能成果展示", 2)
    add_body(
        doc,
        "系统已实现：六智能体可被平台侧发现并完成跨云询价协同；采购后台支持对话驱动采购与 HITL；供应/物流可返回差异化报价与运费；协作过程可在面板观察角色、动作与状态。座椅商城→缺料→询价的演示链路可本地/云上跑通。",
    )
    add_heading(doc, "2. 量化成效分析", 2)
    add_table(
        doc,
        ["指标项", "联调样例结果", "说明"],
        [
            ["平台发现", "platform_adp，候选3，degrade=false", "发现路径走梧桐，非本地伪装"],
            ["发现耗时", "约 29s 量级（样例）", "以当次联调日志为准"],
            ["并行询价", "quotes=3（样例）", "三家供应回执"],
            ["AMP双侧对账", "matched 3/3（样例）", "Access/Message 同任务对齐"],
            ["组群E2E", "PASS；选商供应A，运费276，TCO 19566", "含3出价+3 TCO方案"],
        ],
        "表6　联调量化样例（以证据文件为准）",
    )
    add_body(
        doc,
        "社会效益方面：作品复用开源、贴合国标，降低异构对接的重复工程；场景上服务采销协同，有助于压缩信息甄别与沟通成本；标准化推广上为「协议面稳定 + 业务面创新」提供可复用样本。",
    )
    add_heading(doc, "3. 必要验证场景完成情况", 2)
    add_image(doc, IMG / "ch5-validation.png", "图11　梧桐必要验证完成情况")
    add_table(
        doc,
        ["验证项", "完成情况", "佐证方向"],
        [
            ["注册", "已完成", "AIC登记表/平台回填；ACS提交材料"],
            ["发现", "已完成", "ADP平台命中日志与证据JSON"],
            ["互联", "已完成", "跨云AIP RPC；组群冒烟"],
            ["访问", "技术侧已完成；后台截图待补", "AMP/Kafka/双侧对账可作交互记录；平台访问量截图需控制台人工留存"],
        ],
        "表7　必要验证场景对照",
    )
    add_body(
        doc,
        "说明：赛题要求的「平台后台智能体访问量截图」仍为提交硬门槛。因官方暂未提供访问量查询接口，本作品以 AMP 等工程证据支撑访问过程可证，并在材料提交前补齐控制台/排行榜截图。",
    )
    add_heading(doc, "4. 开放开源贡献（鼓励项）", 2)
    add_body(
        doc,
        "本作品基于 AIP/ACPs 开源栈二次开发。鼓励在梧桐科研平台分享智能体、技能、工具与算法模块；鼓励在 https://atomgit.com/AIP-PUB 与 https://github.com/AIP-PUB 进行代码开源、Issue 反馈与技术分享。相关截图与仓库主页作为加分佐证按实际进展附录提交。",
    )

    # ========== 六 ==========
    add_heading(doc, "六、总结与展望", 1)
    add_heading(doc, "1. 经验总结", 2)
    add_body(
        doc,
        "成功经验：① 先保证协议证据链（注册/发现/互联/访问）再扩展业务炫技；② 容灾与缓存必须可解释，禁止伪造平台命中；③ HITL 让关键确认可控，避免全自动脏数据；④ 双侧 AMP 对账使「访问」可核验。不足：平台后台访问量截图依赖人工与平台能力；供应侧更深异构（如 Java Partner）与异常重协商策略仍可持续增强。",
    )
    add_heading(doc, "2. 未来规划", 2)
    add_body(
        doc,
        "后续将围绕三方面深化：① 标准化落地——完善取证自动化与平台材料包；② 功能拓展——竞价策略、异常重协商、物流需求归一增强；③ 工程推广——强化一键部署、文档与 AIP-PUB 社区反馈，推动「采销智能体互联」样本复用到更多工业供应链场景。",
    )

    # ========== 七 ==========
    add_heading(doc, "七、附录", 1)
    add_body(
        doc,
        "1. 测试数据：联调证据（如 docs/evidence/latest_pair.json、组群E2E记录）、平台访问量截图（提交前补齐）、多智能体联调日志。\n"
        "2. 完整工程源码：开源改造说明、带注释代码包、部署/冒烟脚本。\n"
        "3. 参考文献：见下文。\n"
        "4. 佐证材料：演示视频说明、平台接入录屏、试点/应用证明、软著专利（如有）。\n"
        "5. 开源贡献材料（鼓励）：梧桐分享截图、AIP-PUB 仓库与 Commit/Issue 记录（如有）。",
        first_indent=False,
    )

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
        "[10] Liu J, et al. ACPs: Agent Collaboration Protocols for the Internet of Agents[J/OL]. arXiv:2505.13523, 2025.",
        "[11] 刘军, 等. ACPs：面向智能体互联网的智能体协作协议体系[EB/OL]. 2025.",
        "[12] Liu J, et al. Agent Collaboration Protocols (ACPs) Architecture[EB/OL]. IETF Internet-Draft.",
        "[13] GB/Z 185.1—2026～185.7—2026 人工智能 智能体互联[S]. 2026.",
        "[14] 【国标详解】「四问+一图」读懂《人工智能 智能体互联》系列标准[EB/OL]. 2026.",
        "[15] 刘军. 北邮ACPs协议和代码与智能体互联AIP标准的关系[EB/OL]. 2025.",
        "[16] 刘军. 关于智能体互联协议标准的130天[EB/OL]. 2025.",
        "[17] 刘军. 智能体互联系列国标草案的理解（1）：总体架构设计[EB/OL]. AIP社区, 2025.",
        "[18] 梧桐智能体互联平台[EB/OL]. https://wt.ioa.pub/",
        "[19] O’Reilly T. What Is Web 2.0[EB/OL]. O’Reilly Media, 2005.",
        "[20] Berners-Lee T. Web 3.0 and Linked Data[EB/OL]. W3C, 2009.",
        "[21] Berners-Lee T. Realising the Full Potential of the Web[EB/OL]. W3C, 1998.",
    ]
    for ref in refs:
        p = doc.add_paragraph()
        run = p.add_run(ref)
        set_run_font(run, size=10.5)
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.left_indent = Cm(0.74)
        p.paragraph_format.first_line_indent = Cm(-0.74)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.25

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    OUT2.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT2))
    print("Wrote", OUT)
    print("Wrote", OUT2)
    print("size", OUT.stat().st_size)


if __name__ == "__main__":
    build()
