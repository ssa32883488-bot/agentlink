# -*- coding: utf-8 -*-
"""独立生成第六/七章与参考文献 DOCX，并刷新最终完整版中的对应章节。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _report_common import add_title_block, new_doc, save_doc
from chapter67_body import write_chapter6, write_chapter7, write_references


def build_standalone() -> Path:
    doc = new_doc()
    add_title_block(doc, "第六～七章　总结与展望 · 附录")
    write_chapter6(doc)
    write_chapter7(doc)
    write_references(doc)
    save_doc(
        doc,
        "智能体互联技术报告_第六七章_总结附录.docx",
        "智能体互联技术报告_第六七章_总结附录.docx",
    )
    return HERE / "智能体互联技术报告_第六七章_总结附录.docx"


def main():
    build_standalone()
    # refresh final merge
    from build_chapter34_and_final import main as rebuild_final

    rebuild_final()


if __name__ == "__main__":
    main()
