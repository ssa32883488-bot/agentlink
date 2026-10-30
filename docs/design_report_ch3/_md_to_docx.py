# -*- coding: utf-8 -*-
"""Markdown 报告 → DOCX（含插图），放到同目录并复制桌面。"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent
MD = ROOT / "三_智能体互联技术选型与方案设计.md"
FIGS = ROOT / "figures"
OUT = ROOT / "三_智能体互联技术选型与方案设计.docx"


def set_run_font(run, size=11, bold=False, color=None):
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), "微软雅黑")
    if color:
        run.font.color.rgb = RGBColor(*color)


def add_para(doc, text, *, style=None, size=11, bold=False, center=False, color=None):
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold, color=color)
    return p


def main() -> None:
    text = MD.read_text(encoding="utf-8")
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.2)
    sec.left_margin = Cm(2.2)
    sec.right_margin = Cm(2.2)

    lines = text.splitlines()
    i = 0
    table_buf: list[str] = []

    def flush_table():
        nonlocal table_buf
        if not table_buf:
            return
        rows = []
        for ln in table_buf:
            if re.match(r"^\|?\s*-{3,}", ln.replace("|", " ").strip()) or set(ln.replace("|", "").strip()) <= {"-", ":", " "}:
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cells:
                rows.append(cells)
        table_buf = []
        if len(rows) < 2:
            return
        cols = max(len(r) for r in rows)
        t = doc.add_table(rows=len(rows), cols=cols)
        t.style = "Table Grid"
        for ri, row in enumerate(rows):
            for ci in range(cols):
                cell = t.rows[ri].cells[ci]
                cell.text = row[ci] if ci < len(row) else ""
                for p in cell.paragraphs:
                    for run in p.runs:
                        set_run_font(run, size=9, bold=(ri == 0))
        doc.add_paragraph()

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            table_buf.append(ln)
            i += 1
            continue
        else:
            flush_table()

        if ln.startswith("# "):
            add_para(doc, ln[2:].strip(), size=18, bold=True)
        elif ln.startswith("## "):
            add_para(doc, ln[3:].strip(), size=14, bold=True, color=(31, 56, 100))
        elif ln.startswith("### "):
            add_para(doc, ln[4:].strip(), size=12, bold=True, color=(46, 80, 144))
        elif ln.startswith("#### "):
            add_para(doc, ln[5:].strip(), size=11, bold=True)
        elif ln.startswith("![") and "](" in ln:
            m = re.search(r"!\[(.*?)\]\((.*?)\)", ln)
            if m:
                cap, rel = m.group(1), m.group(2)
                img = (ROOT / rel).resolve()
                if img.is_file():
                    doc.add_picture(str(img), width=Cm(15.5))
                    add_para(doc, cap, size=9, center=True, color=(80, 80, 80))
                else:
                    add_para(doc, f"（缺图 {rel}）", size=10)
        elif ln.startswith("```"):
            buf = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            add_para(doc, "\n".join(buf), size=9)
        elif ln.startswith("> "):
            add_para(doc, ln[2:].strip(), size=10, color=(60, 60, 60))
        elif ln.startswith("- ") or ln.startswith("* "):
            add_para(doc, "• " + ln[2:].strip(), size=11)
        elif re.match(r"^\d+\.\s", ln):
            add_para(doc, ln.strip(), size=11)
        elif ln.strip() == "---":
            pass
        elif ln.strip():
            # bold **x**
            p = doc.add_paragraph()
            parts = re.split(r"(\*\*.*?\*\*)", ln.strip())
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    run = p.add_run(part[2:-2])
                    set_run_font(run, size=11, bold=True)
                else:
                    run = p.add_run(part)
                    set_run_font(run, size=11)
        i += 1
    flush_table()

    doc.save(str(OUT))
    desk = Path.home() / "Desktop" / OUT.name
    shutil.copy2(OUT, desk)
    print("WROTE", OUT)
    print("DESKTOP", desk)


if __name__ == "__main__":
    main()
