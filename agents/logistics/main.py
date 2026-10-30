from __future__ import annotations

import os
from pathlib import Path

import yaml
import uvicorn

from agentlink_runtime.partner_app import build_partner_app
from commerce_v2.partner_logistics import pipeline
from commerce_v2.runtime_flag import use_v2

ROOT = Path(__file__).resolve().parent
POLICY = yaml.safe_load((ROOT / "policy.yaml").read_text(encoding="utf-8"))

os.environ.setdefault("AGENTLINK_RUNTIME", "v2")

app = build_partner_app(
    title="AgentLink Logistics",
    agent_id="logistics",
    tenant_id="logistics-org",
    aic_env="LOGISTICS_AIC",
    default_aic="logistics-local-aic",
    pipeline=pipeline,
    policy=POLICY,
    product_name="shipping_quote",
)

if use_v2():
    from commerce_v2.partner_routes import mount_partner_v2

    mount_partner_v2(app, agent_id="logistics")
else:
    from commerce.office_routes import mount_office

    mount_office(app, agent_id="logistics")


def main() -> None:
    uvicorn.run(
        "agents.logistics.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8015")),
        reload=False,
    )


if __name__ == "__main__":
    main()
