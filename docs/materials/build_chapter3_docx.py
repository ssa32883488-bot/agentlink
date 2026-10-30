# -*- coding: utf-8 -*-
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _report_common import add_title_block, new_doc, save_doc
from chapter3_body import write_chapter3


def build():
    raise SystemExit(
        "第3章已固化（见 docs/materials/frozen/）。禁止再运行本脚本覆盖。"
    )
    doc = new_doc()
    add_title_block(doc, "第三章　技术选型与方案设计（独立扩写稿）")
    write_chapter3(doc)
    save_doc(doc, "智能体互联技术报告_第三章_技术选型与方案设计.docx", "智能体互联技术报告_第三章_技术选型与方案设计.docx")


if __name__ == "__main__":
    build()
