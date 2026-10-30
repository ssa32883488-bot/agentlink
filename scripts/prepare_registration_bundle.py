"""打包六份已定稿 ACS，供官网控制台上传；并写提交状态表。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACS = ROOT / "acs"
OUT = ROOT / "dist" / "registration_bundle"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    files = sorted(ACS.glob("*.acs.json"))
    manifest = {
        "organization": "后浪队",
        "contact": "李佳铖 <3572962849@qq.com>",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "note": "ICP暂无；端点为 HTTP IP:port。公网探测通过后再提交官网。",
        "agents": [],
    }
    for f in files:
        shutil.copy2(f, OUT / f.name)
        data = json.loads(f.read_text(encoding="utf-8"))
        ep = (data.get("endPoints") or [{}])[0].get("url")
        manifest["agents"].append(
            {
                "file": f.name,
                "name": data.get("name"),
                "endpoint": ep,
                "submit_status": "pending_platform_urls",
                "aic": None,
            }
        )
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(files)} ACS)")


if __name__ == "__main__":
    main()
