"""Verify live UI role-theme assets on dual cloud."""
from __future__ import annotations

import hashlib
import json
import ssl
import urllib.request

CTX = ssl.create_default_context()
CTX_INSECURE = ssl._create_unverified_context()


def fetch(url: str, insecure: bool = False) -> bytes:
    ctx = CTX_INSECURE if insecure else CTX
    return urllib.request.urlopen(url, context=ctx, timeout=15).read()


def main() -> None:
    files = [
        ("buyer_css", "https://ashui.online:8090/static/styles.css", False, ["role-buyer", "role-supplier", "role-logistics", "1.45rem"]),
        ("buyer_js", "https://ashui.online:8090/static/app.js", False, ["applyRoleTheme", "resolveUiRole"]),
        ("log_css", "https://ashui.online:8095/static/styles.css", False, ["role-buyer", "role-logistics", "1.45rem"]),
        ("sup_css", "https://39.105.20.113:8091/static/styles.css", True, ["role-supplier", "role-logistics", "1.45rem"]),
        ("buyer_html", "https://ashui.online:8090/", False, ["roleChip", "styles.css"]),
        ("sup_html", "https://39.105.20.113:8091/", True, ["roleChip", "styles.css"]),
    ]
    ok = 0
    for key, url, insecure, checks in files:
        data = fetch(url, insecure=insecure)
        digest = hashlib.sha256(data).hexdigest()[:12]
        text = data.decode("utf-8", "replace")
        miss = [c for c in checks if c not in text]
        if miss:
            print(f"FAIL {key} sha={digest} miss={miss}")
        else:
            ok += 1
            print(f"OK   {key} sha={digest} bytes={len(data)}")

    domains = [
        ("buyer", "https://ashui.online:8090/api/domain", False),
        ("logistics", "https://ashui.online:8095/api/domain", False),
        ("supplier", "https://39.105.20.113:8091/api/domain", True),
    ]
    for name, url, insecure in domains:
        payload = json.loads(fetch(url, insecure=insecure).decode())
        title = payload.get("domain_title") or payload.get("title") or payload
        print(f"domain {name}: {title}")
        ok += 1

    print(f"SUMMARY {ok}/{len(files) + len(domains)}")


if __name__ == "__main__":
    main()
