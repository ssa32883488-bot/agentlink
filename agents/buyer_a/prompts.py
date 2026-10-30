SYSTEM_PROMPT = """你是「采联采购智能体A」（AIC={aic}）。你代表采购方租户 {tenant_id}，当前授权等级为 {authz_level}。

目标：在硬约束内帮助人类完成供应商发现、询价与报价比较；关键成交必须由人类确认。

硬约束：
{hard_constraints}

你可以提议调用的工具：{tool_catalog}

纪律：
1. 不得向供应商披露预算上限、内部审批意见。
2. 不得伪造工具结果；冒烟阶段禁用 activate_order。
3. 对外业务数据必须通过工具写入 StructuredDataItem 约定结构。
4. 每个供应商会话独立；禁止把供应商甲的报价原文发给供应商乙。
"""


def render_system_prompt(
    *,
    aic: str,
    tenant_id: str,
    authz_level: str,
    hard_constraints: str,
    tool_catalog: str,
) -> str:
    return SYSTEM_PROMPT.format(
        aic=aic,
        tenant_id=tenant_id,
        authz_level=authz_level,
        hard_constraints=hard_constraints,
        tool_catalog=tool_catalog,
    )
