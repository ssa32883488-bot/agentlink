# -*- coding: utf-8 -*-
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _report_common import add_title_block, new_doc, save_doc
from chapter2_body import write_chapter2


def build():
    raise SystemExit(
        "第2章已固化（见 docs/materials/frozen/）。禁止再运行本脚本覆盖。"
        "若需改第2章，请直接改用户最终稿后重新 freeze_ch1_to_ch4.py。"
    )
    doc = new_doc()
    add_title_block(doc, "第二章　需求分析（独立扩写稿）")
    write_chapter2(doc)
    save_doc(doc, "智能体互联技术报告_第二章_需求分析.docx", "智能体互联技术报告_第二章_需求分析.docx")


if __name__ == "__main__":
    build()
