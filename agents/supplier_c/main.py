from __future__ import annotations

import os
from pathlib import Path

import yaml
import uvicorn

from agentlink_runtime.partner_app import build_partner_app
from commerce_v2.partner_supplier import pipeline
from commerce_v2.runtime_flag import use_v2

ROOT = Path(__file__).resolve().parent
POLICY = yaml.safe_load((ROOT / "policy.yaml").read_text(encoding="utf-8"))

os.environ.setdefault("AGENTLINK_RUNTIME", "v2")

app = build_partner_app(
    title="供应商C",
    agent_id="supplier-c",
    tenant_id="supplier-org-c",
    aic_env="SUPPLIER_C_AIC",
    default_aic="supplier-c-local-aic",
    pipeline=pipeline,
    policy=POLICY,
    product_name="initial_quote",
)

if use_v2():
    from commerce_v2.partner_routes import mount_partner_v2

    mount_partner_v2(app, agent_id="supplier-c")
else:
    from commerce.supplier_routes import mount_supplier_commerce

    mount_supplier_commerce(app, agent_id="supplier-c")


def main() -> None:
    uvicorn.run(
        "agents.supplier_c.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8014")),
        reload=False,
    )


if __name__ == "__main__":
    main()
