from __future__ import annotations

from typing import Any

from acps_sdk.aip import DataItem, StructuredDataItem, TextDataItem


def wrap_business(
    schema_type: str,
    business_id: str,
    payload: dict[str, Any],
    schema_version: str = "1.0",
) -> dict[str, Any]:
    return {
        "schema_type": schema_type,
        "schema_version": schema_version,
        "business_id": business_id,
        "payload": payload,
    }


def as_structured_item(envelope: dict[str, Any]) -> StructuredDataItem:
    return StructuredDataItem(data=envelope)


def extract_structured(items: list[DataItem] | None) -> dict[str, Any] | None:
    for item in items or []:
        if isinstance(item, StructuredDataItem):
            return item.data
        if isinstance(item, dict) and item.get("type") == "data":
            return item.get("data")
    return None


def extract_text(items: list[DataItem] | None) -> str:
    parts: list[str] = []
    for item in items or []:
        if isinstance(item, TextDataItem):
            parts.append(item.text)
        elif isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(parts)
