"""Deploy buyer V1 tools (Pydantic + Wit caps + UI widgets + memory)."""
from __future__ import annotations

import os
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parents[1]
PEM = Path(os.path.expandvars(r"%USERPROFILE%\.ssh\cursor.pem"))

FILES = [
    "commerce/buyer_tools/__init__.py",
    "commerce/buyer_tools/schemas.py",
    "commerce/buyer_tools/memory_store.py",
    "commerce/buyer_tools/service.py",
    "commerce/chat_buyer_wit.py",
    "agents/buyer_a/AGENTS.md",
    "ui/static/app.js",
    "ui/static/styles.css",
]

REMOTE_CHECK = r"""
cd /opt/agentlink && ./venv/bin/python <<'PY'
from commerce.buyer_tools.service import get_buyer_tools
from commerce.chat_buyer_wit import _build_capabilities, _extract_ui_widgets

caps = _build_capabilities(None)
print("caps", len(caps))
ids = []
for c in caps:
    cid = getattr(c, "id", None)
    if cid is None:
        meta = getattr(c, "__wit_capability__", None) or getattr(c, "__capability__", None)
        cid = getattr(meta, "id", None) if meta is not None else None
    ids.append(cid or getattr(c, "__name__", type(c).__name__))
print("sample_ids", ids[:10])
w = _extract_ui_widgets(
    [
        {
            "result": {
                "case_id": "c",
                "candidates": [{"candidate_id": "x"}],
                "ui_hint": {"form": "shortlist_confirm"},
            }
        }
    ]
)
print("widget", w[0]["kind"] if w else None)
print("mem", get_buyer_tools().memory.inject("smoke-mem", [{"key": "t", "value": 1}])["ok"])
PY
"""


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        "81.70.46.119",
        username="root",
        pkey=paramiko.RSAKey.from_private_key_file(str(PEM)),
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    _, o, _ = c.exec_command(
        "mkdir -p /opt/agentlink/commerce/buyer_tools /opt/agentlink/data/agent_memory",
        timeout=30,
    )
    o.channel.recv_exit_status()
    with SCPClient(c.get_transport()) as scp:
        for rel in FILES:
            scp.put(str(ROOT / rel), f"/opt/agentlink/{rel}")
            print("put", rel)

    cmd = (
        "systemctl restart agentlink-buyer-a agentlink-ui-buyer; sleep 4; "
        "systemctl is-active agentlink-buyer-a agentlink-ui-buyer; "
        + REMOTE_CHECK
        + "; grep -n 'shortlist-form\\|renderUiWidgets\\|discover.suppliers' "
        "/opt/agentlink/ui/static/app.js /opt/agentlink/commerce/chat_buyer_wit.py | head -20; "
        "curl -sk -o /dev/null -w 'health=%{http_code}\\n' https://127.0.0.1:8010/health; "
        "curl -sk -o /dev/null -w 'ui=%{http_code}\\n' https://127.0.0.1:8090/"
    )
    _, stdout, stderr = c.exec_command(cmd, timeout=120, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    print(out)
    if err.strip():
        print("STDERR:", err)
    c.close()


if __name__ == "__main__":
    main()
