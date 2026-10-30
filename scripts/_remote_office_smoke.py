# -*- coding: utf-8 -*-
"""Run on buyer host: /opt/agentlink/.venv/bin/python scripts/_remote_office_smoke.py"""
from __future__ import annotations

import json
import ssl
import urllib.request


def call(path: str, data=None):
    url = "https://127.0.0.1:8010" + path
    req = urllib.request.Request(url, method="GET" if data is None else "POST")
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=ctx, timeout=45) as r:
        return json.loads(r.read().decode())


def main() -> None:
    print("email", call("/api/erp/mailbox").get("email"))
    t = call(
        "/api/erp/tickets",
        {
            "title": "smoke2",
            "kind": "procurement",
            "peer_agent_id": "supplier-a",
            "state": {"a": 1},
        },
    )
    print("ticket", t["id"], t["status"])
    print("suspend", call(f"/api/erp/tickets/{t['id']}/suspend", {"reason": "x", "state": {"a": 2}})["status"])
    print("resume", call(f"/api/erp/tickets/{t['id']}/resume", {})["status"])
    d = call(
        f"/api/erp/tickets/{t['id']}/send-final-docs",
        {
            "to_agent": "supplier-a",
            "order_doc": {"order_no": "EO2", "summary": "o"},
            "invoice_doc": {"invoice_no": "EI2", "summary": "i"},
        },
    )
    print("deliv", (d.get("order_mail") or {}).get("delivery"))
    print("inv_deliv", (d.get("invoice_mail") or {}).get("delivery"))
    tf = call(f"/api/erp/tickets/{t['id']}")
    print("done", tf.get("completion"), tf.get("status"))


if __name__ == "__main__":
    main()
