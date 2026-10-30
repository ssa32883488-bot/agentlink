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
    title="供应商A",
    agent_id="supplier-a",
    tenant_id="supplier-org-a",
    aic_env="SUPPLIER_A_AIC",
    default_aic="supplier-a-local-aic",
    pipeline=pipeline,
    policy=POLICY,
    product_name="initial_quote",
)

if use_v2():
    from commerce_v2.partner_routes import mount_partner_v2

    mount_partner_v2(app, agent_id="supplier-a")
else:
    from commerce.supplier_routes import mount_supplier_commerce
    from agents.supplier_a.graph import run_supplier_pipeline

    def _legacy_pipeline(*, state, envelope, policy):
        return run_supplier_pipeline(state=state, rfq_envelope=envelope, policy=policy)

    # legacy 入口保留旧挂载；默认 v2 不走这里
    mount_supplier_commerce(app, agent_id="supplier-a")


def main() -> None:
    uvicorn.run(
        "agents.supplier_a.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8011")),
        reload=False,
    )


if __name__ == "__main__":
    main()
