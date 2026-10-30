# -*- coding: utf-8 -*-
import json
import ssl
import urllib.error
import urllib.request

CTX = ssl._create_unverified_context()
BASE = "http://39.105.20.113:8093"


def get(url: str, limit: int = 0):
    try:
        with urllib.request.urlopen(url, context=CTX, timeout=15) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return r.status, raw if not limit else raw[:limit]
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, raw if not limit else raw[:limit]
    except Exception as e:  # noqa: BLE001
        return "ERR", f"{type(e).__name__}: {e}"


def main() -> None:
    code, body = get(f"{BASE}/api/domain")
    print("domain", code, body[:120])
    d = json.loads(body) if code == 200 else {}
    agent = (d.get("agents") or [{}])[0].get("id") or "supplier-b"
    paths = [
        "api/erp/chat-engine",
        "api/erp/chat/threads",
        "api/erp/conversations",
        "api/erp/merchant",
        "api/erp/tickets",
        "api/erp/notifications",
        "api/erp/mailbox",
        "api/erp/catalog",
        "api/erp/promotions",
        "api/erp/rfq-inbox",
        "api/erp/inventory",
        "api/erp/sales-orders",
        "api/erp/audit-tasks",
        "api/erp/shared-facts",
        "api/erp/order-provenance/list",
        "api/erp/office-audit",
        "api/erp/workbench-summary",
        "api/v2/health",
        "health",
    ]
    for p in paths:
        c, b = get(f"{BASE}/api/proxy/{agent}/{p}", limit=90)
        print(c, p, b.replace("\n", " "))


if __name__ == "__main__":
    main()
