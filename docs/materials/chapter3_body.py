# -*- coding: utf-8 -*-
"""第三章《智能体互联技术选型与方案设计》（commerce_v2 现行实现）。"""
from __future__ import annotations

from _report_common import IMG, add_body, add_heading, add_image, add_table

FROZEN = False  # 本章按 commerce_v2 设计稿重写，可生成


def write_chapter3(doc) -> None:
    add_heading(doc, "三、智能体互联技术选型与方案设计", 1)
    add_body(
        doc,
        "本章依据附件2大纲撰写。技术基线以本仓库 commerce_v2（AGENTLINK_RUNTIME=v2）现行实现为准，"
        "不以历史 Wit/旧 flow 业务楼为准。配套说明见 docs/commerce_v2_asbuilt.md 与 "
        "commerce_v2/interaction_contract.md。"
        "选型原则：协议平面不改国标骨架，业务平面自主编排；LLM 只做理解与改写，效力动作必须经人断点或 Gate。",
    )

    add_heading(doc, "1. 基础开发资源选型", 2)
    add_heading(doc, "1.1 配套教程与平台环境", 3)
    add_body(
        doc,
        "本作品互联能力建立在国家 AIP 智能体互联标准对应的开源实现与梧桐智能体科研平台通道之上，"
        "遵循「协议平面不改国标骨架、业务平面自主编排」的改造原则。",
    )
    add_table(
        doc,
        ["资源", "选型", "用途"],
        [
            ["开源协议栈", "AIP-PUB / ACPs（acps-sdk）", "AIC/ACS/ADP/AIP/AMP；Partner /rpc；组群 MQ"],
            ["科研平台", "梧桐（wt.ioa.pub）", "Registry/CA、Discovery、访问统计"],
            ["发现", "ADP …/acps-adp-v2/discover", "按改写后需求检索可协作智能体"],
            ["交互", "AIP Task + HTTPS /rpc；国标 Group MQ", "点对点询价/议价/下单；组群共同上下文"],
            ["访问", "Kafka amp.access / amp.message", "双侧访问记账（Leader send / Partner receive）"],
            ["安全", "平台证书 + mTLS；组群 AIC=证书 CN", "跨云身份与传输"],
        ],
        "表3-1　平台与协议资源选型",
    )
    add_body(
        doc,
        "遵循思路：AIC（身份）→ ACS（描述）→ ADP（发现）→ AIP/Group（交互）→ AMP（访问）"
        "五类能力一一映射工程模块；业务字段进入 structured 扩展位，不改 Task 骨架。"
        "发现失败可标注降级来源，禁止把本地黄页伪装成 platform_adp。",
    )

    add_heading(doc, "1.2 开发软硬件与运行时选型", 3)
    add_table(
        doc,
        ["层次", "选型", "理由（相对旧 Wit 主路径）"],
        [
            ["语言/服务", "Python ≥3.12 + FastAPI + uvicorn", "与 ACPs 生态一致；六体各自暴露 HTTPS API 与 /rpc"],
            ["业务编排", "commerce_v2 确定性路径编排", "采购主路径不再依赖 Wit 工具乱序；状态机可测可演示"],
            ["认知组件", "DeepSeek（OpenAI 兼容）仅用于需求改写消歧", "改写进 llm_rewrite；效力动作不由模型口头确认"],
            ["Partner 智力", "partner_supplier / partner_logistics 确定性信封", "目录计价、政策、运力可验收；可对接 Java Partner"],
            ["主数据", "每智能体 SQLite 分库 + data/v2_* JSON", "禁止跨域直连库；工单确认态以库为准"],
            ["前端", "六体独立控制台（静态页+本域代理）", "AskUser 与 Gate 分离；组群置顶聊天室"],
            ["部署", "双云 systemd：腾讯采购+物流；阿里供应", "贴近跨企业拓扑"],
        ],
        "表3-2　运行时与业务资源选型",
    )
    add_body(
        doc,
        "模型边界（硬约束）：LLM 只做「理解与改写」；短名单确认、是否组群、买法决断、"
        "place_order=on、工单 ack 等必须经人断点或 Gate 写库。",
    )

    add_heading(doc, "1.3 对 AIP 国标的工程映射", 3)
    add_table(
        doc,
        ["国标能力", "工程落点（现行）"],
        [
            ["AIC", "各体 .env 中证书 CN；组群 leader_aic_for"],
            ["ACS", "acs/*.acs.json 入驻描述"],
            ["ADP", "protocol_bridge.discover_suppliers / discover_suppliers_for_brief（多 SKU 并集）"],
            ["AIP", "aip_call → Partner /rpc；信封 schema_type=v2.*"],
            ["Group", "group_mq 开群邀请；transport=group 成功才标国标通道"],
            ["AMP", "Leader/Partner 双侧 Access+Message，messageId=msg-{taskId}"],
        ],
        "表3-3　国标能力与工程落点",
    )

    add_heading(doc, "2. 核心技术方案设计", 2)
    add_heading(doc, "2.1 整体架构：五层多智能体分层互联", 3)
    add_body(
        doc,
        "系统采用五层架构（见图3-1）：人机交互层承接 AskUser 断点、Gate 工单与组群聊天室；"
        "智能体运行时层部署六体进程；业务编排层承载普通十点路径与组群主持竞价；"
        "协议适配层复用 ACPs 核心能力；双云部署层落实跨企业拓扑。梧桐 Registry/CA/Discovery/Kafka 横向贯通。",
    )
    add_image(doc, IMG / "ch3-v2-architecture.png", "图3-1　采联 AgentLink 五层架构（commerce_v2）")
    add_table(
        doc,
        ["产品支柱", "方案体现"],
        [
            ["多智能体互联", "ADP 发现 → AIP 并行询价 / 国标组群出价 → 共享订单确认"],
            ["人在断点", "短名单、议价、买法、是否组群、方案采纳、工单 ack"],
            ["全员够智力", "供应答规格/价/政策；物流给运力方案；采购能改写与主持"],
        ],
        "表3-4　三根产品支柱",
    )

    add_heading(doc, "2.2 协议复用与自主创新边界", 3)
    add_image(doc, IMG / "ch3-v2-reuse-innovate.png", "图3-2　开源复用与自主创新边界（commerce_v2）")
    add_table(
        doc,
        ["类别", "内容", "是否改国标结构"],
        [
            ["复用", "acps-sdk Task/RPC、Discovery、证书、Kafka AMP、Group 邀请协议", "否"],
            ["适配", "payload 封装、mTLS、自签邀请开关、live AIC 绑定、发现缓存", "否（工程封装）"],
            [
                "创新（commerce_v2）",
                "确定性双路径、AskUser/Gate 分离、多品 items[] 全覆盖、组群聊天室按行出价、place_order=on 工具闸",
                "否（业务层）",
            ],
            ["禁止", "伪造 platform_adp；未确认即 RFQ/开群；对话声称已生效而 ack=false", "—"],
        ],
        "表3-5　复用 / 适配 / 创新 / 禁止事项",
    )
    add_body(
        doc,
        "二次开发表述：在 AIP/ACPs 开源互联栈与梧桐通道上深度二次开发——不改国标报文骨架，"
        "自主完成采销「人在环双路径」编排、采购主持组群竞价、多品全覆盖与跨云部署，"
        "使「能发现、能调用、能统计」落地为可演示、可确认的工业采购协同。",
    )

    add_heading(doc, "2.3 关键技术选型", 3)
    add_heading(doc, "（1）智能体注册与发现", 3)
    add_body(
        doc,
        "六体各自 ACS 入驻，平台发证后 AIC=证书 CN 回填运行环境。"
        "采购以改写后的完整需求句（可含多品）调用 ADP；discover_suppliers_for_brief 对 brief.items[] "
        "做 SKU 并集召回，避免「脚轮+坐垫」只命中一家品类。"
        "发现结果进入短名单 UI；断点①前人不得自动发 RFQ / 自动开群。",
    )
    add_heading(doc, "（2）跨智能体数据传输", 3)
    add_body(
        doc,
        "点对点：v2.initial_quote / v2.bargain / v2.promo_query / v2.place_order / v2.logistics_quote 等结构化信封。"
        "组群：采购主持 open_group → 成员 join → 群内按行 v2.group_bid；失败可 force_local 续跑，"
        "但不得伪称 transport=group。效力字段：共享 order_id / logistics_id；供应工具仅当 place_order=on 落单。",
    )
    add_heading(doc, "（3）协同调度（业务状态机）", 3)
    add_body(
        doc,
        "硬编排：Phase 状态机决定合法迁移。软入口：对话只触发已注册路径函数；AskUser 挂起等人；"
        "Gate 为工单页写 ack。普通路径：改写→发现→短名单→初报→议价 Ask→买法→下单 Gate→物流。"
        "组群路径：冲突建议→「我要组群竞价」→勾选成员→主持开群→按行报价→全量覆盖方案→拆单工单。",
    )
    add_heading(doc, "（4）安全交互与鉴权", 3)
    add_body(
        doc,
        "默认平台证书 + mTLS；组群邀请跨云自签场景可配置关闭校验（工程开关，材料中如实说明）。"
        "工单确认以 buyer_ack / supplier_ack / effective 为准；物流 Gate 使用 logistics ticket id。",
    )

    add_heading(doc, "2.4 业务双路径详细设计（现行）", 3)
    add_heading(doc, "2.4.1 普通采购路径", 3)
    add_body(
        doc,
        "用户需求经 LLM 改写产出 items[]，经 ADP 并集发现后进入短名单；"
        "人确认并询价后并行初报，再经「是否探优惠」「怎么买」等 AskUser 断点，"
        "以 place_order=on 落共享订单并经 Gate 双边确认，最后询运与物流 Gate"
        "（路径概览见图3-3，业务流程图见图3-4，跨角色时序见图3-5）。"
        "模块：buyer_path_normal.py、demand_items.py、llm_rewrite.py、protocol_bridge.py、partner_supplier.py。",
    )
    add_image(doc, IMG / "ch3-v2-normal-path.png", "图3-3　普通采购路径概览（AskUser 断点与 Gate）")
    add_image(doc, IMG / "ch3-v2-flow-normal.png", "图3-4　普通采销业务流程图")
    add_image(doc, IMG / "ch3-v2-seq-normal.png", "图3-5　普通采销场景时序图")

    add_heading(doc, "2.4.2 组群竞价路径", 3)
    add_body(
        doc,
        "复杂/冲突场景下用户发起「我要组群竞价」，勾选供应±物流并确认后，由采购智能体主持开群"
        "（优先国标 Group MQ），按供应目录能力逐行 group_bid 并合入物流，"
        "决断全量覆盖拆单或单家全包，再生成系列工单"
        "（路径概览见图3-6，业务流程图见图3-7，跨角色时序见图3-8）。"
        "铁律：主持=采购智能体；开群前必须人确认；汇总须覆盖全部需求行或显式标 missing；"
        "入组不足时早停并显式回退 transport=rpc，禁止静默伪装组群成功。"
        "模块：buyer_path_group.py、group_room.py、group_mq.py 与前端组群聊天室。",
    )
    add_image(doc, IMG / "ch3-v2-group-path.png", "图3-6　组群竞价路径概览（采购主持）")
    add_image(doc, IMG / "ch3-v2-flow-group.png", "图3-7　组群竞价业务流程图")
    add_image(doc, IMG / "ch3-v2-seq-group.png", "图3-8　组群竞价场景时序图")

    add_heading(doc, "2.4.3 AskUser 与 Gate 分离", 3)
    add_table(
        doc,
        ["机制", "入口", "作用"],
        [
            ["AskUser", "choice_actions / shortlist_confirm", "选题推进阶段"],
            ["Gate", "工单 ack-order / ack-logistics", "写确认态产生效力"],
        ],
        "表3-6　AskUser 与 Gate 分工",
    )

    add_heading(doc, "2.5 六智能体角色设计（部署视图）", 3)
    add_table(
        doc,
        ["智能体", "云", "API", "UI", "职责摘要"],
        [
            ["buyer-a", "腾讯", "8010", "8090", "Leader；普通/组群编排；组群主持"],
            ["buyer-b", "腾讯", "8012", "8092", "同契约第二采购租户"],
            ["logistics", "腾讯", "8015", "8095", "运力方案与物流工单"],
            ["supplier-a", "阿里", "8011", "8091 HTTPS", "脚轮等结构件；满减政策"],
            ["supplier-b", "阿里", "8013", "8093 HTTPS", "面料/坐垫；MOQ/满减"],
            ["supplier-c", "阿里", "8014", "8094 HTTPS", "脚轮+坐垫；紧缺/替代"],
        ],
        "表3-7　六智能体部署与职责",
    )
    add_body(doc, "供应控制台须使用 HTTPS 访问（端口仅挂载 TLS）。", first_indent=True)

    add_heading(doc, "2.6 多品全覆盖设计要点", 3)
    add_body(
        doc,
        "工业采购常一次点名多品类。方案层强制：① brief.items[] 为权威行项目；"
        "② 防幻觉仅拦截「用户未提脚轮却改写成脚轮」；③ 发现按 SKU 并集；"
        "④ 组群按行出价；汇总主推「全量覆盖」拆单。",
    )

    add_heading(doc, "3. 方案对大纲硬性目标的覆盖", 2)
    add_table(
        doc,
        ["硬性目标", "方案落点"],
        [
            ["接入梧桐：注册→发现→互联→访问", "ACS/AIC + ADP + AIP/Group + AMP"],
            ["自动发现与跨端访问", "platform_adp 优先；跨云 /rpc"],
            ["业务场景", "座椅原料采购：普通询价 + 组群竞价"],
            ["可验证", "双云 systemd；UI 双路径截图与日志；访问量后台截图（材料硬门槛）"],
        ],
        "表3-8　硬性目标覆盖矩阵",
    )
