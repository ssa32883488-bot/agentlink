"""供应商共用：议价/竞价/合同确认 + 被动物流询运。"""

__all__ = ["attach_freight", "dispatch_extra_schemas", "enrich_initial_quote"]


def __getattr__(name: str):
    if name == "attach_freight":
        from agents.supplier_common.freight import attach_freight

        return attach_freight
    if name in ("dispatch_extra_schemas", "enrich_initial_quote"):
        from agents.supplier_common import negotiate

        return getattr(negotiate, name)
    raise AttributeError(name)
