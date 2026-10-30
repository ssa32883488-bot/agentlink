# -*- coding: utf-8 -*-
"""整合技术方案最终完整版 DOCX。

规则（2026-10-30 固化）：
- 第1～4章：只读使用 frozen/chapters_01_04_frozen.docx（用户已改，禁止脚本覆盖）
- 第5～7章与参考文献：可继续生成/替换
- 拼装方式：整包复制固化稿为底稿再追加，避免丢失图片
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from docx import Document
from docx.oxml.ns import qn

from _report_common import DESKTOP, MATERIALS, add_heading, save_doc
from chapter67_body import write_chapter6, write_chapter7, write_references

FROZEN_CH14 = MATERIALS / "frozen" / "chapters_01_04_frozen.docx"
CH5 = MATERIALS / "智能体互联技术报告_第五章_应用成效.docx"


def _paragraph_text(p_elem) -> str:
    texts = []
    for node in p_elem.iter():
        if node.tag == qn("w:t") and node.text:
            texts.append(node.text)
    return "".join(texts).strip()


def _insert_before_sect(master: Document, node) -> None:
    body = master.element.body
    sect = body[-1]
    if sect.tag == qn("w:sectPr"):
        sect.addprevious(node)
    else:
        body.append(node)


def append_docx_body(
    master: Document,
    path: Path,
    *,
    start_contains: str,
    chapter_h1: str | None = None,
):
    """追加另一文档正文（不含其封面）；图片关系可能不完整，第5章宜少依赖跨包图片或后补。"""
    if not path.exists():
        add_heading(master, chapter_h1 or path.name, 1)
        from _report_common import add_body

        add_body(master, f"【缺失分章文稿：{path.name}】", first_indent=False)
        return

    if chapter_h1:
        add_heading(master, chapter_h1, 1)

    sub = Document(str(path))
    started = False
    for child in list(sub.element.body):
        if child.tag == qn("w:sectPr"):
            continue
        if not started:
            if child.tag != qn("w:p"):
                continue
            if start_contains in _paragraph_text(child):
                started = True
            else:
                continue
        _insert_before_sect(master, deepcopy(child))


def build():
    if not FROZEN_CH14.exists():
        raise SystemExit(
            "未找到 frozen/chapters_01_04_frozen.docx。请先运行 freeze_ch1_to_ch4.py"
        )

    # 以固化第1～4章整包为底稿，保留全部图片/媒体
    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "work.docx"
        shutil.copy2(FROZEN_CH14, work)
        doc = Document(str(work))

        append_docx_body(
            doc,
            CH5,
            start_contains="1. 功能成果展示",
            chapter_h1="五、应用成效",
        )
        write_chapter6(doc)
        write_chapter7(doc)
        write_references(doc)

        name = "智能体互联技术报告_最终完整版.docx"
        # 先落到 materials
        out_m = MATERIALS / name
        doc.save(str(out_m))
        print("saved", out_m, out_m.stat().st_size)

        alt2 = MATERIALS / "智能体互联技术报告_完整版.docx"
        try:
            doc.save(str(alt2))
            print("saved", alt2)
        except PermissionError:
            print("skip locked", alt2)

        # 桌面另存拼装版，绝不覆盖用户「_新稿」
        desk_assemble = DESKTOP / "智能体互联技术报告_最终完整版_拼装版.docx"
        try:
            doc.save(str(desk_assemble))
            print("saved", desk_assemble)
        except PermissionError:
            print("desktop assemble locked")

        # 可选：若桌面最终完整版未被占用，同步；失败则跳过
        try:
            doc.save(str(DESKTOP / name))
            print("saved", DESKTOP / name)
        except PermissionError:
            print("desktop 最终完整版 locked; keep 用户_新稿 untouched")


if __name__ == "__main__":
    build()
