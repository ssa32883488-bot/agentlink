# -*- coding: utf-8 -*-
import json
from pathlib import Path

from wit.acps.acs_contract import validate_registry_acs

acs = Path(__file__).resolve().parents[1] / "acs"
for p in sorted(acs.glob("*.acs.json")):
    data = json.loads(p.read_text(encoding="utf-8"))
    try:
        validate_registry_acs(data)
        print(
            "OK",
            p.name,
            "skills",
            len(data.get("skills") or []),
            "validity",
            (data.get("certificate") or {}).get("requestedValidity"),
        )
    except Exception as e:  # noqa: BLE001
        print("FAIL", p.name, type(e).__name__, e)
