# -*- coding: utf-8 -*-
"""生成 commerce_v2 第三/四章独立稿，并与固化第1～2章、现有第5～7章拼装最终版。"""
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

from _report_common import (
    DESKTOP,
    MATERIALS,
    add_title_block,
    new_doc,
    save_doc,
)
from chapter3_body import write_chapter3
from chapter4_body import write_chapter4
from chapter67_body import write_chapter6, write_chapter7, write_references

FROZEN_DIR = MATERIALS / "frozen"
FROZEN_CH14_OLD = FROZEN_DIR / "chapters_01_04_frozen.docx"
FROZEN_CH12 = FROZEN_DIR / "chapters_01_02_frozen.docx"
FROZEN_CH14_NEW = FROZEN_DIR / "chapters_01_04_frozen.docx"
CH5 = MATERIALS / "智能体互联技术报告_第五章_应用成效.docx"
CH3_OUT = "智能体互联技术报告_第三章_技术选型与方案设计.docx"
CH4_OUT = "智能体互联技术报告_第四章_项目实施.docx"


def _ptext(elem) -> str:
    return "".join(n.text or "" for n in elem.iter() if n.tag == qn("w:t")).strip()


def _insert_before_sect(master: Document, node) -> None:
    body = master.element.body
    sect = body[-1]
    if sect.tag == qn("w:sectPr"):
        sect.addprevious(node)
    else:
        body.append(node)


def extract_ch12_from_old_freeze() -> Path:
    """从旧 1～4 固化稿截取至「三、」之前，保留图片。"""
    src = FROZEN_CH14_OLD
    if not src.exists():
        # fallback: full user snapshot
        src = FROZEN_DIR / "最终完整版_用户固化快照.docx"
    if not src.exists():
        raise SystemExit("缺少固化快照，无法保留第1～2章")

    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, FROZEN_CH12)
    doc = Document(str(FROZEN_CH12))
    body = doc.element.body
    removing = False
    to_remove = []
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        if not removing and child.tag == qn("w:p"):
            t = _ptext(child)
            if t.startswith("三、") or t.startswith("四、") or t.startswith("五、"):
                removing = True
        if removing:
            to_remove.append(child)
    for child in to_remove:
        body.remove(child)
    doc.save(str(FROZEN_CH12))
    print("saved ch1-2 freeze", FROZEN_CH12, FROZEN_CH12.stat().st_size)
    return FROZEN_CH12


def append_docx_from_marker(master: Document, path: Path, start_contains: str, chapter_h1: str | None = None):
    if chapter_h1:
        from _report_common import add_heading

        add_heading(master, chapter_h1, 1)
    sub = Document(str(path))
    started = False
    for child in list(sub.element.body):
        if child.tag == qn("w:sectPr"):
            continue
        if not started:
            if child.tag != qn("w:p"):
                continue
            if start_contains in _ptext(child):
                started = True
            else:
                continue
        _insert_before_sect(master, deepcopy(child))


def build_standalone_chapters():
    # ch3
    doc3 = new_doc()
    add_title_block(doc3, "第三章　智能体互联技术选型与方案设计（commerce_v2）")
    write_chapter3(doc3)
    save_doc(doc3, CH3_OUT, CH3_OUT)
    # ch4
    doc4 = new_doc()
    add_title_block(doc4, "第四章　智能体互联项目实施（commerce_v2）")
    write_chapter4(doc4)
    save_doc(doc4, CH4_OUT, CH4_OUT)


def rebuild_ch14_freeze_and_final():
    ch12 = extract_ch12_from_old_freeze()
    ch3 = MATERIALS / CH3_OUT
    ch4 = MATERIALS / CH4_OUT

    # 新 1～4 固化：复制 ch12 为底，追加三、四章正文（含图片关系：章节独立稿自带图）
    # 注意：跨文档 deepcopy 图片可能丢关系；因此最终拼装以 ch12 底稿 + 追加章节内容，
    # 并把新 ch3/ch4 整包另存；最终版用「ch12底稿 + 写入 write_chapter3/4（图片路径本地）」。
    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "final.docx"
        shutil.copy2(ch12, work)
        doc = Document(str(work))
        write_chapter3(doc)
        write_chapter4(doc)

        # 更新 1～4 固化快照（含新三、四）
        doc.save(str(FROZEN_CH14_NEW))
        print("updated", FROZEN_CH14_NEW, FROZEN_CH14_NEW.stat().st_size)

        # 追加第5～7章
        if CH5.exists():
            append_docx_from_marker(
                doc,
                CH5,
                start_contains="1. 功能成果展示",
                chapter_h1="五、应用成效",
            )
        write_chapter6(doc)
        write_chapter7(doc)
        write_references(doc)

        out_name = "智能体互联技术报告_最终完整版.docx"
        out_m = MATERIALS / out_name
        doc.save(str(out_m))
        print("saved", out_m, out_m.stat().st_size)
        try:
            doc.save(str(MATERIALS / "智能体互联技术报告_完整版.docx"))
        except PermissionError:
            pass
        # 桌面：拼装版 + 尝试最终版
        desk_a = DESKTOP / "智能体互联技术报告_最终完整版_拼装版.docx"
        doc.save(str(desk_a))
        print("saved", desk_a)
        try:
            doc.save(str(DESKTOP / out_name))
            print("saved desktop final")
        except PermissionError:
            print("desktop final locked; 拼装版已更新")

    # README note
    (FROZEN_DIR / "FROZEN_README.md").write_text(
        "\n".join(
            [
                "# 固化说明（更新）",
                "",
                "- 第1～2章：仍以用户固化稿为准（`chapters_01_02_frozen.docx`）。",
                "- 第3～4章：已按 commerce_v2 设计稿重写并生成新图，写入 `chapters_01_04_frozen.docx`。",
                "- 第5～7章：仍可继续改。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main():
    build_standalone_chapters()
    rebuild_ch14_freeze_and_final()


if __name__ == "__main__":
    main()
