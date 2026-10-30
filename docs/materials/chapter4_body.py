# -*- coding: utf-8 -*-
"""第四章《智能体互联项目实施》（commerce_v2 现行实现）。"""
from __future__ import annotations

from _report_common import IMG, add_body, add_code, add_heading, add_image, add_table

FROZEN = False


def write_chapter4(doc) -> None:
    add_heading(doc, "四、智能体互联项目实施", 1)
    add_body(
        doc,
        "本章对应大纲「四、智能体互联项目实施」。"
        "实施对象：commerce_v2 双路径采销协同（腾讯采购云 × 阿里供应云）。"
        "验收证据目录示例：docs/evidence/v2_dual_20261030_194944/。",
    )

    add_heading(doc, "1. 项目背景与需求", 2)
    add_heading(doc, "1.1 业务背景", 3)
    add_body(
        doc,
        "智能办公家具场景下，座椅原料（脚轮、面料、坐垫等）需跨企业完成「寻源—议价—下单—物流」闭环。"
        "传统方式依赖人工多轮询价；本作品将流程交由多智能体按 AIP 国标互联，并在关键节点保留人确认。",
    )
    add_heading(doc, "1.2 建设目标（可验收）", 3)
    add_body(
        doc,
        "① 梧桐全链路：六体入驻发证、ADP 发现、AIP/组群交互、AMP 访问统计可查；"
        "② 双路径业务：普通采购询价与采购主持组群竞价均可端到端跑通；"
        "③ 人在环效力：短名单/议价/买法/组群确认用 AskUser，订单与物流用 Gate 工单 ack；"
        "④ 多品全覆盖：一次需求含脚轮+坐垫等时，发现并集、组群按行报价、汇总不漏项；"
        "⑤ 双云真实部署：腾讯采购侧与阿里供应侧分域运行，控制台 HTTPS 可访问。",
    )
    add_heading(doc, "1.3 需求边界", 3)
    add_table(
        doc,
        ["纳入", "不纳入（本期）"],
        [
            ["结构化询价/议价/下单/物流信封", "真实支付与仓储 WMS"],
            ["国标组群优先 + 可声明的本地降级", "改写 Wit 旧主路径作为默认演示"],
            ["LLM 需求改写", "模型口头下单生效"],
            ["六体独立库与工单", "跨域直连对方数据库"],
        ],
        "表4-1　实施需求边界",
    )

    add_heading(doc, "2. 整体架构落地", 2)
    add_heading(doc, "2.1 双云拓扑", 3)
    add_image(doc, IMG / "ch4-v2-dual-cloud.png", "图4-1　双云六体部署拓扑")
    add_table(
        doc,
        ["区域", "智能体", "API", "UI"],
        [
            ["腾讯云", "buyer-a / buyer-b / logistics", "8010 / 8012 / 8015", "8090 / 8092 / 8095"],
            ["阿里云", "supplier-a / b / c", "8011 / 8013 / 8014", "8091 / 8093 / 8094（HTTPS）"],
        ],
        "表4-2　双云端口一览",
    )
    add_body(
        doc,
        "采购作为 Leader 发起发现与组群；供应/物流作为 Partner 收 /rpc 并双侧记 AMP。",
    )

    add_heading(doc, "2.2 运行时开关", 3)
    add_code(
        doc,
        "export AGENTLINK_RUNTIME=v2   # 启用 commerce_v2 主路径\n"
        "# 旧 commerce/_legacy 仅保留 Group MQ 等协议适配，不再作为业务默认楼",
        "代码片段4-1　运行时切换",
    )

    add_heading(doc, "2.3 模块落位", 3)
    add_table(
        doc,
        ["目录/文件", "实施职责"],
        [
            ["commerce_v2/buyer_path_normal.py", "普通十点路径"],
            ["commerce_v2/buyer_path_group.py", "组群主持与竞价汇总"],
            ["commerce_v2/demand_items.py", "多品解析与防幻觉"],
            ["commerce_v2/llm_rewrite.py", "DeepSeek 改写"],
            ["commerce_v2/protocol_bridge.py", "ADP / AIP / AMP 桥"],
            ["commerce_v2/group_room.py", "组群会话与前端聊天室数据"],
            ["commerce_v2/partner_*.py", "供应/物流 Partner 智力"],
            ["commerce_v2/interaction_contract.md", "AskUser / Gate 契约"],
            ["ui/static/*", "短名单、组群室、工单 Gate"],
        ],
        "表4-3　模块落位",
    )

    add_heading(doc, "3. 关键技术实施", 2)
    add_heading(doc, "3.1 智能体注册与发现", 3)
    add_body(
        doc,
        "实施步骤：① 为六体准备 ACS 并在梧桐入驻，证书落地，AIC=证书 CN 写入环境；"
        "② 采购侧配置 Discovery URL（acps-adp-v2/discover）；"
        "③ 用户输入需求 → llm_rewrite 产出 rewritten + items[]；"
        "④ discover_suppliers_for_brief 对每个 SKU 检索后做供应并集，写入短名单；"
        "⑤ UI 展示候选；用户点「确认并询价」或「我要组群竞价」后方可出网。"
        "验收点：返回体含 platform_adp 或诚实标注降级来源；多品需求下短名单覆盖相关品类供应。",
    )

    add_heading(doc, "3.2 跨智能体数据传输", 3)
    add_table(
        doc,
        ["信封 schema", "方向", "作用"],
        [
            ["v2.initial_quote", "采→供", "初报"],
            ["v2.bargain / v2.promo_query", "采→供", "议价/优惠"],
            ["v2.place_order（place_order=on）", "采→供", "落单"],
            ["v2.logistics_quote 等", "采→物", "运力方案"],
            ["v2.group_bid", "群内", "按行出价"],
        ],
        "表4-4　主要结构化信封",
    )
    add_body(
        doc,
        "组群实施：采购主持调用开群（group_mq），成员以证书身份 join；"
        "群内按目录能力发送 v2.group_bid，物流合入运力；前端组群聊天室展示过程，结束后可折叠摘要；"
        "transport=group 仅在真实国标通道成功时标记。"
        "共享标识：订单/物流 id 写入双方工单，Gate 双边 ack 后标 effective。",
    )

    add_heading(doc, "3.3 协同调度实施", 3)
    add_body(
        doc,
        "普通路径与 UI 断点对齐：改写与发现→短名单 AskUser→并行初报→是否探优惠 AskUser→"
        "可选议价→买法 AskUser→工具闸 place_order=on→订单 Gate→人确认后询运→物流 Gate。"
        "组群路径：冲突/复杂建议→「我要组群竞价」→勾选供应±物流→「确认组群竞价」→"
        "开群与按行出价→全量覆盖方案决断→拆单工单系列确认。"
        "调度原则：Phase 非法迁移拒绝；对话不直接写效力字段。"
        "业务流程图与跨角色时序图见第三章图3-4～图3-5（普通采销）、图3-7～图3-8（组群竞价）；"
        "本章实施以双云拓扑与里程碑为主（图4-1、图4-2）。",
    )
    add_image(doc, IMG / "ch3-v2-flow-normal.png", "图4-3　普通采销业务流程图（实施对照）")
    add_image(doc, IMG / "ch3-v2-flow-group.png", "图4-4　组群竞价业务流程图（实施对照）")

    add_heading(doc, "3.4 安全交互与鉴权实施", 3)
    add_body(
        doc,
        "① 生产默认校验证书链；组群跨云自签时使用约定工程开关并在材料中披露；"
        "② Partner 校验来访任务与 AIC 绑定；"
        "③ 供应侧拒绝无 place_order=on 的落单请求；"
        "④ 控制台：采购/物流可用 HTTP 或 HTTPS；供应 UI 强制 HTTPS，避免浏览器「网络错误」。",
    )

    add_heading(doc, "3.5 人机与工单实施", 3)
    add_table(
        doc,
        ["能力", "实现要点"],
        [
            ["AskUser", "choice_actions 渲染为按钮；短名单确认组件"],
            ["Gate", "/tickets 列表；ack-order / ack-logistics"],
            ["组群室", "置顶可折叠；按消息流展示出价"],
            ["清理", "scripts/_clear_history_and_tickets.py 演示前清场"],
        ],
        "表4-5　人机与工单实施要点",
    )

    add_heading(doc, "4. 实施过程与里程碑", 2)
    add_image(doc, IMG / "ch4-v2-milestones.png", "图4-2　commerce_v2 实施里程碑")
    add_table(
        doc,
        ["阶段", "工作内容", "结果"],
        [
            ["M1 协议底座", "ACS/AIC、ADP、AIP、AMP、双云 systemd", "六体可发现可调用"],
            ["M2 commerce_v2 骨架", "切运行时、确定性 Phase、AskUser/Gate", "普通路径可演示"],
            ["M3 组群竞价", "主持开群、按行 bid、聊天室、全覆盖汇总", "组群路径可演示"],
            ["M4 多品与体验", "items 并集发现、组群折叠、供应 HTTPS", "脚轮+坐垫不漏项"],
            ["M5 材料固化", "双路径截图+日志、asbuilt、本章文档", "参赛/软著材料就绪"],
        ],
        "表4-6　实施里程碑",
    )
    add_body(
        doc,
        "实施中关键修复：组群 SSL 邀请在自签环境可配置信任策略；"
        "多品改写防幻觉与发现并集，避免坐垫漏项；"
        "组群聊天室可收起，避免占满对话区；"
        "供应控制台改 HTTPS 消除跨站/混合内容类网络错误。",
    )

    add_heading(doc, "5. 测试与验证", 2)
    add_heading(doc, "5.1 功能验证清单", 3)
    add_table(
        doc,
        ["编号", "场景", "通过标准"],
        [
            ["T1", "普通询价（单品或清晰短名单）", "初报→议价可选→下单 Gate→物流"],
            ["T2", "组群竞价（脚轮+坐垫等多品）", "开群成功或诚实降级；汇总覆盖全部行"],
            ["T3", "发现真实性", "非伪造 platform_adp"],
            ["T4", "工具闸", "无 place_order=on 不落单"],
            ["T5", "访问统计", "梧桐后台可见双侧调用增量"],
            ["T6", "供应 UI", "https://<host>:8091|8093|8094 可开"],
        ],
        "表4-7　功能验证清单",
    )
    add_heading(doc, "5.2 证据包与回归脚本", 3)
    add_body(
        doc,
        "证据包建议结构：docs/evidence/<batch_id>/screenshots、logs、README.md。"
        "回归脚本：_check_services.py（健康）、_capture_v2_dual_inquiry_shots.py（双路径截图）、"
        "_clear_history_and_tickets.py（清场）、_fix_supplier_uis.py（供应 UI HTTPS 排查）。",
    )

    add_heading(doc, "6. 与梧桐平台对接说明", 2)
    add_body(
        doc,
        "① 注册：六 ACS 入驻，证书落地，AIC 回填；"
        "② 发现：采购以改写需求调用平台 Discovery；"
        "③ 互联：HTTPS /rpc 承载 AIP Task，组群走平台 MQ；"
        "④ 访问：Leader/Partner 写 Kafka 主题，作品材料附平台访问量截图。"
        "对接原则：协议平面跟国标与平台；业务平面用 commerce_v2 自研编排——二次开发边界清晰，便于评审查验。",
    )

    add_heading(doc, "7. 实施总结", 2)
    add_body(
        doc,
        "本项目在 AIP/ACPs 与梧桐通道上完成工业采销多智能体互联落地："
        "以 commerce_v2 确定性双路径替代不可控的工具乱序调用；"
        "以 AskUser/Gate 保证人在环效力；以多品并集与组群按行出价保证复杂需求可覆盖；"
        "以双云六体证明跨企业可部署。"
        "后续可在不改国标骨架前提下扩展更多品类 ACS、加强组群失败自动恢复策略，"
        "以及把访问统计看板嵌入控制台。",
    )
