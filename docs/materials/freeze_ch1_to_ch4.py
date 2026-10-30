# -*- coding: utf-8 -*-
"""从用户已改的最终稿固化第1～4章（整包复制后截断，保留图片）。"""
from __future__ import annotations

import shutil
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

DESKTOP = Path(r"C:\Users\32081\Desktop")
MATERIALS = Path(r"f:\code\智能体协议\项目开发\agentlink\docs\materials")
FROZEN = MATERIALS / "frozen"
FROZEN.mkdir(parents=True, exist_ok=True)

CANDIDATES = [
    DESKTOP / "智能体互联技术报告_最终完整版_新稿.docx",
    DESKTOP / "智能体互联技术报告_最终完整版.docx",
    MATERIALS / "智能体互联技术报告_最终完整版.docx",
    MATERIALS / "智能体互联技术报告_完整版.docx",
]


def _ptext(elem) -> str:
    return "".join(n.text or "" for n in elem.iter() if n.tag == qn("w:t")).strip()


def _is_cut_marker(text: str) -> bool:
    return text.startswith("五、") or text.startswith("参考文献")


def main() -> None:
    src = next((p for p in CANDIDATES if p.exists()), None)
    if src is None:
        raise SystemExit("找不到可固化的最终稿 docx")

    full_snap = FROZEN / "最终完整版_用户固化快照.docx"
    ch14 = FROZEN / "chapters_01_04_frozen.docx"
    meta = FROZEN / "FROZEN_README.md"

    shutil.copy2(src, full_snap)
    shutil.copy2(src, ch14)
    print("snapshot full <-", src)

    # 在副本上删除「五、」及之后的正文，保留图片关系
    doc = Document(str(ch14))
    body = doc.element.body
    removing = False
    to_remove = []
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        if not removing and child.tag == qn("w:p"):
            if _is_cut_marker(_ptext(child)):
                removing = True
        if removing:
            to_remove.append(child)
    for child in to_remove:
        body.remove(child)

    doc.save(str(ch14))
    print("saved frozen ch1-4", ch14, "removed_tail", len(to_remove))
    print("size_bytes", ch14.stat().st_size)

    meta.write_text(
        "\n".join(
            [
                "# 第1～4章已固化（请勿再脚本覆盖）",
                "",
                f"- 来源快照：`{full_snap.name}`（完整用户稿）",
                f"- 固化切片：`{ch14.name}`（整包复制后截去「五、」及之后，保留图片）",
                f"- 来源文件：`{src}`",
                "",
                "## 规则",
                "- **一、二、三、四章**：以本目录固化稿为准；禁止用 chapter1/2/3_body 或 build_chapter4 覆盖。",
                "- **五、六、七章及参考文献**：仍可继续改写与重建。",
                "- `build_final_report.py`：前半部拼接本切片，再追加第5～7章。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("wrote", meta)


if __name__ == "__main__":
    main()
