"""打包 agentlink 部署包（不含 .venv / 本地数据）。"""
from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]  # 智能体协议
OUT = ROOT / "dist" / "agentlink_remote.tar.gz"
STAGING = ROOT / "dist" / "_staging"


def main() -> None:
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True)
    dest = STAGING / "agentlink"
    ignore = shutil.ignore_patterns(
        ".venv",
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
        "data",
        "workspaces",
        "dist",
        ".env",
        "*.sqlite3",
        ".git",
        ".tools",  # gradle 发行包，云端不需要
        "node_modules",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.mp4",
        "build",
        "bin",
        "obj",
        ".gradle",
    )
    shutil.copytree(ROOT, dest, ignore=ignore)
    # 再砍材料/证据大图与 java 本地工具残留
    for rel in (
        "docs/materials",
        "docs/evidence",
        "java-suppliers/.tools",
        "scripts/_e2e_docx_builder",
    ):
        p = dest / rel
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    # vendor wheels / sdk next to package for offline install
    vendor = STAGING / "vendor"
    vendor.mkdir()
    sdk = REPO / "ACPs-community" / "acps-sdk"
    if sdk.is_dir():
        shutil.copytree(
            sdk,
            vendor / "acps-sdk",
            ignore=shutil.ignore_patterns(".venv", "__pycache__", ".git", ".pytest_cache", "*.pyc"),
        )
    wit = REPO / "wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl"
    if wit.is_file():
        shutil.copy2(wit, vendor / wit.name)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with tarfile.open(OUT, "w:gz") as tar:
        tar.add(STAGING / "agentlink", arcname="agentlink")
        tar.add(vendor, arcname="vendor")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
