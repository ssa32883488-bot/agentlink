import pytest

from agentlink_runtime.authz import AuthzLevel, allows
from agentlink_runtime.gateway import AgentContext, ToolGateway, ToolSpec


@pytest.mark.asyncio
async def test_activate_denied_at_negotiate():
    gw = ToolGateway()

    async def boom(args, ctx):
        return {"activated": True}

    gw.register(
        ToolSpec(name="activate_order", authz_min=AuthzLevel.COMMIT, handler=boom, human_confirm=True)
    )
    ctx = AgentContext(
        agent_id="buyer-a",
        aic="x",
        tenant_id="buyer-org-a",
        authz_level=AuthzLevel.NEGOTIATE,
        business_id="b1",
    )
    result = await gw.execute(ctx, "activate_order", {})
    assert result.ok is False
    assert result.status == "AUTHZ_INSUFFICIENT"


def test_authz_rank():
    assert allows(AuthzLevel.COMMIT, AuthzLevel.NEGOTIATE)
    assert not allows(AuthzLevel.SUGGEST, AuthzLevel.NEGOTIATE)
