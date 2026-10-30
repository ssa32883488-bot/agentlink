# -*- coding: utf-8 -*-
"""独立撰写技术方案第四章《项目实施》DOCX（详细扩写稿）。"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

IMG = Path(r"f:\code\智能体协议\outputs\custom-imagegen")
OUT = Path(r"C:\Users\32081\Desktop\智能体互联技术报告_第四章_项目实施.docx")
OUT2 = Path(r"f:\code\智能体协议\项目开发\agentlink\docs\materials\智能体互联技术报告_第四章_项目实施.docx")


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


def add_image(doc, path: Path, caption: str, width_cm=15.2):
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


def add_code(doc, text: str, caption: str | None = None):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.font.name = "Consolas"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(9)
    if caption:
        add_caption(doc, caption)


def build():
    raise SystemExit(
        "第4章已固化（见 docs/materials/frozen/）。禁止再运行本脚本覆盖。"
        "若需改第4章，请直接改用户最终稿后重新 freeze_ch1_to_ch4.py。"
    )
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.5)
    sec.right_margin = Cm(2.5)
    sec.top_margin = Cm(2.5)
    sec.bottom_margin = Cm(2.5)

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("AIC·智能体互联技术方案")
    set_run_font(r, east="黑体", size=18, bold=True)

    st = doc.add_paragraph()
    st.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = st.add_run("第四章　项目实施（独立扩写稿）")
    set_run_font(r2, east="黑体", size=16, bold=True)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r3 = sub.add_run("作品：采联 AgentLink —— 异构采销多智能体互联协同系统")
    set_run_font(r3, size=12)

    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rn = note.add_run("（全文不出现参赛单位校名、LOGO与指导教师信息；合并完整版时可删本节标题页）")
    set_run_font(rn, size=10.5)
    rn.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    add_body(
        doc,
        "本章对应附件2「项目实施」要求，分两节展开：①整体实施方案——给出完整开发流程、"
        "2026年9月15日至10月20日的分期计划、软硬件资源配置与三人分工；"
        "②关键技术落地实现——围绕开源二次开发、AIP 协议适配与梧桐平台接入全流程，"
        "结合模块流图、交互时序图与核心代码片段说明兼容性问题和优化对策。"
        "叙述以仓库真实模块与部署事实为准，不虚构接口能力。",
    )

    # ==================== 1 ====================
    add_heading(doc, "1. 整体实施方案", 2)

    add_heading(doc, "1.1 完整开发流程", 3)
    add_body(
        doc,
        "实施主线严格按「需求拆解 → 开源代码适配改造 → AIP 标准兼容开发 → 梧桐平台对接调试 → 全功能联调测试」推进，"
        "并在联调阶段叠加双云部署与证据采集，形成可提交的协议证据链。各阶段目标与产物如下。",
    )
    add_table(
        doc,
        ["阶段", "核心目标", "关键产物"],
        [
            [
                "需求拆解",
                "把赛题四步（注册/发现/互联/访问）映射为采销六体场景与验收口径",
                "场景说明书、六体角色表、验收清单、模块边界图",
            ],
            [
                "开源适配改造",
                "引入 acps-sdk / wit-framework，搭起 Agent 进程与配置骨架",
                "可启动的 buyer/supplier/logistics 进程、ACS 草稿、环境模板",
            ],
            [
                "AIP 标准兼容",
                "结构化任务收发、Partner 确定性回执、采购案状态机与 HITL",
                "aip_start_structured、Partner /rpc、procurement_case、工具网关",
            ],
            [
                "梧桐对接调试",
                "完成 ACS 提交与 AIC 回填；平台 ADP 发现；AMP Kafka 上报",
                "登记材料、platform_adp 命中日志、amp.access/message 记录",
            ],
            [
                "全功能联调测试",
                "跨云并行询价、组群竞价/TCO、控制台对话与证据固化",
                "双链路冒烟报告、UI 实拍、metrics 快照、材料包",
            ],
        ],
        "表4-1　五阶段开发流程与产物",
    )
    add_body(
        doc,
        "流程上强调「协议证据先于业务炫技」：任一业务功能若不能在平台发现、跨云 AIP 与 AMP 访问上留下可核验痕迹，"
        "不得计入验收完成。容灾路径必须显式标注（如 degrade、transport=rpc），禁止把本地补齐伪装成平台命中。",
    )

    add_heading(doc, "1.2 开发周期与里程碑（2026-09-15～2026-10-20）", 3)
    add_body(
        doc,
        "立项至搭建完毕共约五周（含国庆档期并行推进文档与联调准备）。周期按五个阶段切块，"
        "并设置四个里程碑控制风险：M1 六体骨架可启动；M2 跨云 AIP 互通；M3 梧桐平台发现命中；"
        "M4 普通询价与组群竞价双链路证据齐备。甘特示意见图4-1。",
    )
    add_image(doc, IMG / "ch4-schedule.png", "图4-1　开发周期甘特示意（2026-09-15～2026-10-20）")
    add_table(
        doc,
        ["阶段", "时间窗口", "主要工作", "里程碑"],
        [
            [
                "P0 立项与需求拆解",
                "9/15–9/21",
                "研读赛题与 GB/Z 185 / AIP 资料；定义座椅原料采销场景；"
                "划定六智能体职责与双云拓扑；形成验收口径（注册/发现/互联/访问）",
                "需求基线冻结",
            ],
            [
                "P1 开源适配改造",
                "9/22–9/28",
                "接入 acps-sdk 2.2.0 与 wit-framework；搭建 agents/* 进程与 pyproject；"
                "准备 ACS JSON、证书目录与 .env；本地单机冒烟启动",
                "M1 六体骨架可启动",
            ],
            [
                "P2 AIP 标准兼容开发",
                "9/29–10/5",
                "实现 Leader 结构化 AIP 发起与 Partner /rpc 回执；采购案状态机与 HITL 四态；"
                "ToolGateway 与买方工具（发现/询价/下单）；供应侧目录报价 graph",
                "M2 跨云 AIP 互通（初通）",
            ],
            [
                "P3 梧桐平台对接调试",
                "10/6–10/12",
                "ACS 提交与 AIC 回填；ADP 平台发现（含缓存/refresh）；"
                "AMP Access/Message 写本地并上报 Kafka；组群 MQ 绑定与身份策略调试",
                "M3 平台发现命中 platform_adp",
            ],
            [
                "P4 全功能联调测试",
                "10/13–10/20",
                "腾讯云/阿里云正式部署；并行 RFQ、议价与组群竞价 TCO；"
                "六体控制台联调；取证脚本与材料整理；缺陷收敛",
                "M4 双链路证据齐备",
            ],
        ],
        "表4-2　分期计划与里程碑",
    )
    add_body(
        doc,
        "周期约束下的并行策略：P2 与 P3 存在交叉——业务状态机可在平台证书未齐时用弱身份绑定联调，"
        "但验收截图必须以平台路径为准；P4 前三天锁定缺陷只修阻塞项，后四天固化证据与文档，避免无限功能扩张。",
    )

    add_heading(doc, "1.3 软硬件资源配置", 3)
    add_table(
        doc,
        ["类别", "配置项", "说明"],
        [
            ["云主机·腾讯云", "ashui.online / 81.70.46.119", "部署采购商A/B、物流及其控制台（API 8010/8012/8015，UI 8090/8092/8095）"],
            ["云主机·阿里云", "39.105.20.113", "部署供应商A/B/C及其控制台（API 8011/8013/8014，UI 8091/8093/8094）"],
            ["平台服务", "wt.ioa.pub", "Registry/CA、Discovery（ADP）、Kafka（wt.ioa.pub:19092）、组群 MQ（:5671）"],
            ["运行时", "Python ≥3.12、FastAPI", "协议与编排主栈；供应 A 另含 Java/LangChain4j 异构 Partner 样例"],
            ["开源依赖", "acps-sdk 2.2.0、wit-framework 2.1.0", "AIP/ACPs 协议实现与对话编排框架"],
            ["模型服务", "DeepSeek（OpenAI 兼容）", "采购/供应侧 Wit 对话意图与工具规划（业务决策仍以状态机为准）"],
            ["数据", "SQLite 分库", "buyer-a/b、supplier-a/b/c 业务库隔离；采购案 JSON 分文件存储"],
            ["证书与安全", "平台证书 + 云主机 HTTPS", "腾讯云 Let's Encrypt；阿里云 IP 自签需信任包与 hostname 策略"],
            ["开发机", "Windows 工作站", "编码、Playwright 取证、远程部署脚本（pack/deploy_remote）"],
        ],
        "表4-3　软硬件与平台资源配置",
    )
    add_body(
        doc,
        "资源原则：协议面统一接入梧桐，业务面按角色跨云拆分，以真实跨域时延与证书差异暴露兼容问题；"
        "演示级 ERP 用 SQLite 降低运维成本，但 AIP/AMP 路径与生产形态一致，避免「本地假互联」。",
    )

    add_heading(doc, "1.4 团队成员分工（成员A/B/C）", 3)
    add_body(
        doc,
        "团队三人，按「协议与平台 / 采购域业务 / 供应物流与增强」切分，接口处通过状态机字段、"
        "AIP schema 与 AMP taskId 对齐，减少口头耦合。",
    )
    add_table(
        doc,
        ["成员", "职责主线", "负责模块/工作包", "阶段侧重"],
        [
            [
                "成员A",
                "协议平面与梧桐接入、双云部署运维",
                "ACS/AIC 注册材料与回填；commerce/discovery、amp_log；"
                "agentlink_runtime/mtls、aip_client_util、partner_app；"
                "deploy_remote / remote_install；Kafka/MQ 联通与对账脚本",
                "P0 拓扑定稿；P1/P3 主力；P4 证据与稳定性",
            ],
            [
                "成员B",
                "采购域编排与人机协同",
                "commerce/procurement_case、hitl_gate、flow_service、buyer_tools；"
                "chat_buyer_wit 与 ToolGateway；buyer-a/b 控制台与商城入口；"
                "普通询价主路径与 HITL 交互文案",
                "P0 验收口径；P2 主力；P4 对话演示与 UI 取证",
            ],
            [
                "成员C",
                "供应/物流 Partner 与协同增强",
                "agents/supplier_*、logistics 与 supplier_common 目录报价；"
                "chat_supplier_wit；group_mq、scheme_planner、组群竞价/TCO；"
                "supplier/logistics 控制台与异构 Java Partner 对接验证",
                "P1 Partner 骨架；P2/P3 报价与组群；P4 竞价链路冒烟",
            ],
        ],
        "表4-4　三人分工矩阵",
    )
    add_body(
        doc,
        "协作机制：每日短同步阻塞项；接口变更必须更新 schema_type / 状态机 ALLOWED 表；"
        "联调缺陷按「协议阻断 > 跨云连通 > 业务体验」分级。成员A对平台材料与访问证据负责，"
        "成员B对采购主路径演示负责，成员C对供应差异化回执与组群路径负责。",
    )

    # ==================== 2 ====================
    add_heading(doc, "2. 关键技术落地实现", 2)

    add_heading(doc, "2.1 总体模块结构与主路径", 3)
    add_body(
        doc,
        "系统按四层落地：表现层（六体独立控制台与商城）、业务编排层（Wit 对话、采购案状态机、HITL、工具网关）、"
        "协议平面（ADP/AIP/AMP/组群 MQ）、运行与部署（双云进程、证书、Kafka）。"
        "开源基座提供报文与 SDK 能力，自主创新集中在采销编排、证据链与跨云运维。模块分层见图4-2；"
        "采购协同主路径见图4-3。",
    )
    add_image(doc, IMG / "ch4-module-flow.png", "图4-2　采联 AgentLink 模块分层与数据流")
    add_image(doc, IMG / "ch4-procurement-seq.png", "图4-3　采购协同主路径（对话→发现→询价→竞价/下单→AMP留痕）")

    add_heading(doc, "2.2 开源代码二次开发过程", 3)
    add_body(
        doc,
        "（1）基座引入。以 AIP-PUB/ACPs 社区实现 acps-sdk（工程内 editable，版本 2.2.0）为协议内核，"
        "复用 AipRpcClient、TaskCommand/TaskResult、Partner RPC 服务端与可选组群 Leader/Partner 组件；"
        "对话侧引入 wit-framework 2.1.0，将自然语言意图映射到受控工具集，避免模型直接改写协议字段。",
    )
    add_body(
        doc,
        "（2）适配层封装。在 agentlink_runtime 增加：aip_payload（业务 envelope 与 structured dataItem 互转）、"
        "aip_client_util（Leader 一键发起并写 AMP）、partner_app（统一 /rpc 入口与 receive 侧 AMP）、"
        "mtls（双云证书与 hostname 策略）、gateway.ToolGateway（鉴权、幂等、human_confirm→NEED_HUMAN）。"
        "上述封装不修改国标报文结构，只补齐工程缺口。",
    )
    add_body(
        doc,
        "（3）业务层二次开发。commerce 域实现采购案持久化与状态机、平台发现缓存、并行 RFQ、议价与组群竞价、"
        "scheme_planner 多方案 TCO、双侧 AMP 本地 NDJSON + Kafka 上报、分角色 ERP/库存工具。"
        "相对官方 demo 的三点差异：①跨云双侧 AMP 同 taskId 对账；②对话驱动 + HITL 四态门禁；"
        "③ADP 平台优先且容灾标注诚实（禁止本地补齐伪装 platform_adp）。",
    )
    add_body(
        doc,
        "（4）异构扩展。供应侧以 Python 确定性 graph 为主，并保留 Java/LangChain4j Partner 接入样例，"
        "验证同一 AIP 任务面上「实现语言可异构、回执 schema 可对齐」。目录缺货时返回可解释错误，而非空成功。",
    )

    add_heading(doc, "2.3 AIP 标准协议适配逻辑", 3)
    add_body(
        doc,
        "适配逻辑可概括为「业务 envelope → AIP TaskCommand.Start → Partner TaskResult → 业务回执解析 → AMP 留痕」。"
        "Leader 侧核心函数 aip_start_structured 负责构造 TaskCommand，经 AipRpcClient 发往 Partner URL，"
        "并从 products.dataItems 提取结构化结果；同时以 direction=send 调用 record_access。",
    )
    add_code(
        doc,
        "async def aip_start_structured(...):\n"
        "    client = AipRpcClient(partner_url=..., leader_id=leader_aic,\n"
        "        expected_partner_aic=partner_aic,\n"
        "        identity_binding_enabled=os.getenv(\"AIP_IDENTITY_BINDING\",\"0\")==\"1\",\n"
        "        ssl_context=build_client_ssl_context())\n"
        "    command = TaskCommand(..., command=TaskCommandType.Start, taskId=task_id,\n"
        "        dataItems=[as_structured_item(envelope)])\n"
        "    response = await client._send_request(command)\n"
        "    # 解析 TaskResult.products → envelope；record_access(direction=\"send\")",
        "代码片段4-1　Leader 侧 AIP 结构化发起（agentlink_runtime/aip_client_util.py）",
    )
    add_body(
        doc,
        "Partner 侧由 build_partner_app 暴露 /rpc，校验任务后进入角色 graph，产出可审计报价/运费/拒绝原因，"
        "并以 direction=receive 写 AMP。身份绑定通过环境变量开关：联调期可弱绑定降低证书摩擦，"
        "组群平面可独立设置 ACPS_GROUP_IDENTITY_BINDING，避免 HTTP 平面与 AMQP user_id 策略互相拖死。",
    )
    add_body(
        doc,
        "采购案状态机保证 AIP 调用落在合法业务相位。状态集合含 DRAFT、DISCOVERING、SHORTLIST_PENDING、"
        "SOURCING、COMPARE_PENDING、NEGOTIATING/BIDDING 及其审查态，直至 ORDER_DRAFT、CONTRACT_PENDING、ACTIVE。"
        "非法迁移直接拒绝，配合 HITL（approve/edit/reject/respond）防止未确认短名单或脏下单。",
    )
    add_code(
        doc,
        "STATES = (\"DRAFT\",\"DISCOVERING\",\"SHORTLIST_PENDING\",\"SOURCING\",\n"
        "         \"COMPARE_PENDING\",\"NEGOTIATING\",\"BIDDING\", ...)\n"
        "ALLOWED = {\n"
        "  \"DRAFT\": {\"DISCOVERING\",\"EXCEPTION\"},\n"
        "  \"DISCOVERING\": {\"SHORTLIST_PENDING\",\"EXCEPTION\"},\n"
        "  \"SHORTLIST_PENDING\": {\"SOURCING\",\"DISCOVERING\",\"EXCEPTION\"},\n"
        "  \"SOURCING\": {\"COMPARE_PENDING\",\"EXCEPTION\"},\n"
        "  \"COMPARE_PENDING\": {\"NEGOTIATING\",\"BIDDING\",\"ORDER_DRAFT\",\"EXCEPTION\"}, ...\n"
        "}",
        "代码片段4-2　采购案状态与合法迁移（commerce/procurement_case.py）",
    )

    add_heading(doc, "2.4 梧桐智能体互联平台接入全流程", 3)
    add_body(
        doc,
        "接入按赛题四步落地：注册 → 发现 → 互联 → 访问。流程总览见图4-4。",
    )
    add_image(doc, IMG / "ch4-wutong-seq.png", "图4-4　梧桐接入全流程（注册→发现→互联→访问）")

    add_heading(doc, "（1）智能体注册（ACS / AIC）", 3)
    add_body(
        doc,
        "六智能体分别维护 acs/*.acs.json，描述名称、技能、端点与能力声明。通过 finalize_acs / enroll_platform "
        "等脚本完成平台侧提交与 AIC 回填；回填后的 AIC 与证书 CN、环境变量保持一致，否则后续发送会触发 "
        "SenderIdentityMismatch。注册材料与清单归档于 docs/平台注册清单.md、docs/平台AIC登记表.md。"
        "该步骤由成员A牵头，成员B/C核对各自角色技能描述与公网 RPC URL。",
    )

    add_heading(doc, "（2）智能体发现（ADP）", 3)
    add_body(
        doc,
        "发现统一走梧桐 Discovery：ACPS_DISCOVERY_URL（默认 https://wt.ioa.pub/discovery）下 "
        "POST …/acps-adp-v2/discover（兼容回退 /discover）。编排层实现短 TTL 缓存（默认 60s）与 bypass_cache/refresh，"
        "二次演示可加速，但取证时强制 refresh 以证明真平台命中。候选写入 source=platform_adp，"
        "并用环境变量中的 live AIC/RPC 覆盖平台可能过期的登记，避免「发现到旧端点」。",
    )
    add_code(
        doc,
        "async def discover_suppliers(query=..., *, limit=5, bypass_cache=False):\n"
        "    # 1) TTL 缓存命中则返回 cache_hit=True\n"
        "    # 2) POST {ACPS_DISCOVERY_URL}/acps-adp-v2/discover\n"
        "    # 3) _acs_to_candidate(..., source=\"platform_adp\")\n"
        "    # 4) _bind_live_peer 用 env 中 AIC/RPC 覆盖过期登记\n"
        "    # 5) 凑齐 supplier-a/b/c 后再结束；平台未命中不伪装本地黄页为平台结果",
        "代码片段4-3　平台 ADP 发现主逻辑（commerce/discovery.py）",
    )
    add_body(
        doc,
        "发现耗时常见为十余秒量级（平台往返），属可观测正常现象；联调面板展示 elapsed_ms_platform 与 degrade 标志，"
        "便于评审区分「慢但真」与「快但假」。",
    )

    add_heading(doc, "（3）智能体通信（AIP 互联）", 3)
    add_body(
        doc,
        "短名单经 HITL 确认后进入 SOURCING，Leader 对多家供应并行发起询价任务（同一 business_id/case_id）。"
        "Partner 按目录定价、促销规则或缺货策略回执；编排层汇总为 COMPARE_PENDING，并在协作面板展示 "
        "Leader→Partner 的状态与时延。组群竞价路径优先走平台 MQ（transport=group）；"
        "若组群平面不可用，则显式回退 transport=rpc 完成出价，禁止静默伪装。",
    )
    add_code(
        doc,
        "auction_meta = {\"transport\": \"rpc\"}   # 默认/回退标注\n"
        "if use_group:\n"
        "    try:\n"
        "        ...  # 组群 MQ 竞价，成功则 transport=group 并带 schemes\n"
        "    except ...:\n"
        "        bids = []\n"
        "if not bids:\n"
        "    auction_meta = {\"transport\": \"rpc\"}\n"
        "    for partner in case[\"shortlist\"]:\n"
        "        out = await aip_start_structured(...)  # RPC 逐家取价",
        "代码片段4-4　组群竞价与 RPC 可解释回退（commerce/flow_service.py）",
    )

    add_heading(doc, "（4）访问留痕（AMP）", 3)
    add_body(
        doc,
        "每次 AIP 交互在 Leader send 与 Partner receive 双侧调用 record_access：本地追加 NDJSON，"
        "并向 Kafka 主题 amp.access / amp.message 上报（broker wt.ioa.pub:19092），correlationId/taskId 对齐。"
        "采购 Leader 暴露 GET /api/flow/metrics 聚合 Access/Message、唯一 taskId 与成功率，支撑第五章量化。"
        "说明：AMP 可证明「访问过程」发生，但不能替代赛方要求的平台后台访问量截图。",
    )
    add_code(
        doc,
        "def record_access(*, task_id, local_aic, peer_aic, direction, endpoint=None, status=\"ok\", ...):\n"
        "    access = _build_access_record(...)\n"
        "    message = _build_message_record(...)  # messageId 与 taskId 配对\n"
        "    _append_jsonl(_ACCESS_LOG, access)\n"
        "    _append_jsonl(_MESSAGE_LOG, message)\n"
        "    _publish(\"amp.access\", access, key=task_id)\n"
        "    _publish(\"amp.message\", message, key=task_id)",
        "代码片段4-5　AMP 双侧访问记录与 Kafka 上报（commerce/amp_log.py）",
    )

    add_heading(doc, "2.5 兼容性问题与优化方案", 3)
    add_table(
        doc,
        ["问题", "现象/影响", "优化方案"],
        [
            [
                "跨云证书不一致",
                "腾讯云 LE 与阿里云 IP 自签并存，TLS/hostname 校验失败",
                "统一信任包 + build_client_ssl_context；IP 访问可关闭严格 hostname；公网 URL 与 ACS 端点对齐",
            ],
            [
                "发现时延长、易误判失败",
                "ADP 往返十余秒，重复点击造成重复压测",
                "编排层 TTL 缓存 + 显式 refresh；UI 展示平台耗时；取证强制 bypass_cache",
            ],
            [
                "平台 AIC 与运行证书 CN 漂移",
                "SenderIdentityMismatch / 发往过期端点",
                "发现后 _bind_live_peer 用 env 覆盖；注册回填检查清单化",
            ],
            [
                "身份绑定过严阻塞联调",
                "HTTP 平面与组群 AMQP user_id 策略冲突",
                "AIP_IDENTITY_BINDING 与 ACPS_GROUP_IDENTITY_BINDING 分平面配置",
            ],
            [
                "组群 MQ 不稳定",
                "竞价中断导致业务黑盒失败",
                "失败显式 transport=rpc 回退并写入 auction_meta；历史 E2E 保留 group 主路径证据",
            ],
            [
                "异构供应目录不一致",
                "部分 SKU 仅一家有货，易被误认为互联失败",
                "缺货返回可解释错误；报价表区分 ok/error；演示数据集可切换「三家齐报」",
            ],
            [
                "模型幻觉改写业务字段",
                "对话直接下单或伪造平台命中",
                "工具网关 + 状态机门禁；HITL 短名单/方案确认；协议字段只由代码写入",
            ],
        ],
        "表4-5　兼容性问题与优化对策",
    )
    add_body(
        doc,
        "实施阶段的经验沉淀为三条工程约束：①证据可解释优于体验平滑；②容灾必须打标；"
        "③业务创新不得破坏国标报文。据此，P4 联调将普通询价与组群竞价都纳入脚本化取证，"
        "为第五章应用成效提供可复核输入。",
    )

    add_heading(doc, "2.6 本章工程索引", 3)
    add_table(
        doc,
        ["路径", "用途"],
        [
            ["commerce/discovery.py", "梧桐 ADP 发现、缓存、live 绑定"],
            ["agentlink_runtime/aip_client_util.py", "Leader AIP 结构化发送 + AMP send"],
            ["agentlink_runtime/partner_app.py", "Partner /rpc + AMP receive"],
            ["commerce/amp_log.py", "Access/Message 与 Kafka 上报"],
            ["commerce/procurement_case.py", "采购案状态机"],
            ["commerce/hitl_gate.py", "HITL 四态门禁"],
            ["commerce/flow_service.py", "询价/竞价编排与 rpc 回退"],
            ["agentlink_runtime/gateway.py", "ToolGateway"],
            ["scripts/finalize_acs.py / enroll_platform.py", "注册提交与入驻"],
            ["scripts/deploy_remote.py", "双云部署"],
            ["docs/agent_portals.md", "六体门户与端口总表"],
        ],
        "表4-6　第四章关键工程索引",
    )

    OUT2.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT2))
    print("saved", OUT2)
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(OUT))
        print("saved", OUT)
    except PermissionError:
        alt = OUT.with_name(OUT.stem + "_详细稿" + OUT.suffix)
        doc.save(str(alt))
        print("desktop locked; saved", alt)


if __name__ == "__main__":
    build()
