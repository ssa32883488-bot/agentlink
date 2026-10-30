"""Assert buyer Message send ↔ supplier Message receive same taskId/messageId."""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))
EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "latest_pair.json"


def connect(host: str, *, password: str | None = None) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if password:
        c.connect(host, username="root", password=password, timeout=40, allow_agent=False, look_for_keys=False)
    else:
        c.connect(
            host,
            username="root",
            pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
            timeout=40,
            allow_agent=False,
            look_for_keys=False,
        )
    return c


def main() -> None:
    if not EVIDENCE.is_file():
        raise SystemExit(f"missing {EVIDENCE}; run demo_acps_evidence first")
    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    pairs = (ev.get("amp_buyer") or {}).get("pairs") or []
    if not pairs:
        raise SystemExit("no buyer pairs in evidence")
    want = {p["taskId"]: p["messageId"] for p in pairs}
    print("want", want)

    supplier = connect("39.105.20.113", password=os.environ.get("DEPLOY_PASSWORD", "Aljc3208106930@"))
    _, o, _ = supplier.exec_command(
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "p=Path('/opt/agentlink/logs/amp_message.jsonl')\n"
        "rows=[]\n"
        "if p.exists():\n"
        "  for line in p.read_text(encoding='utf-8').splitlines()[-200:]:\n"
        "    try: rows.append(json.loads(line))\n"
        "    except: pass\n"
        "print(json.dumps(rows, ensure_ascii=False))\n"
        "PY",
        timeout=60,
        get_pty=True,
    )
    raw = o.read().decode("utf-8", errors="replace").strip()
    # last JSON array line
    rows = json.loads(raw.splitlines()[-1] if raw else "[]")
    recv = {}
    for r in rows:
        if (r.get("body") or {}).get("eventType") != "receive":
            continue
        tid = r.get("correlationId") or r.get("correlation_id")
        mid = (r.get("body") or {}).get("messageId")
        if tid:
            recv[str(tid)] = mid
    matched = []
    missing = []
    for tid, mid in want.items():
        if tid in recv and recv[tid] == mid:
            matched.append(tid)
        else:
            missing.append({"taskId": tid, "want_mid": mid, "got_mid": recv.get(tid)})
    report = {
        "matched": matched,
        "missing": missing,
        "matched_count": len(matched),
        "wanted_count": len(want),
        "pass": len(matched) == len(want) and len(want) > 0,
    }
    out = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "bilateral_assert.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("AMP_BILATERAL_PASS" if report["pass"] else "AMP_BILATERAL_FAIL")
    supplier.close()
    raise SystemExit(0 if report["pass"] else 2)


if __name__ == "__main__":
    main()
