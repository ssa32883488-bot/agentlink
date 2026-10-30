# -*- coding: utf-8 -*-
"""Shared helpers for AIC technical report DOCX builders."""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

IMG = Path(r"f:\code\智能体协议\outputs\custom-imagegen")
SHOT = Path(r"f:\code\智能体协议\项目开发\agentlink\docs\evidence\chapter5_run\screenshots")
MATERIALS = Path(r"f:\code\智能体协议\项目开发\agentlink\docs\materials")
DESKTOP = Path(r"C:\Users\32081\Desktop")


def set_run_font(run, *, east="宋体", ascii_font="Times New Roman", size=12, bold=False):
    run.font.name = ascii_font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east)
    run.font.size = Pt(size)
    run.bold = bold


def add_heading(doc, text, level=1):
    p = doc.add_paragraph()
    run = p.add_run(text)
    if level == 1:
        set_run_font(run, east="黑体", size=16, bold=True)
    elif level == 2:
        set_run_font(run, east="黑体", size=14, bold=True)
    else:
        set_run_font(run, east="楷体", size=12, bold=True)
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    return p


def add_body(doc, text, *, first_indent=True):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=12)
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.space_after = Pt(6)
    if first_indent:
        pf.first_line_indent = Cm(0.74)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def add_caption(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=10.5, bold=True)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.first_line_indent = Cm(0)


def add_placeholder(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Cm(0)
    run = p.add_run(text)
    set_run_font(run, size=11, bold=True)
    run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(8)


def add_image(doc, path: Path, caption: str, width_cm=15.2):
    if not path.exists():
        add_body(doc, f"【插图缺失：{path.name}】", first_indent=False)
        add_caption(doc, caption)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Cm(0)
    run = p.add_run()
    run.add_picture(str(path), width=Cm(width_cm))
    add_caption(doc, caption)


def add_table(doc, headers, rows, caption=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        r = cell.paragraphs[0].add_run(h)
        set_run_font(r, east="黑体", size=10.5, bold=True)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = ""
            r = cell.paragraphs[0].add_run(str(val))
            set_run_font(r, size=10.5)
    if caption:
        add_caption(doc, caption)
    doc.add_paragraph()


def add_code(doc, text: str, caption: str | None = None):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.font.name = "Consolas"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(9)
    if caption:
        add_caption(doc, caption)


def new_doc() -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.5)
    sec.right_margin = Cm(2.5)
    sec.top_margin = Cm(2.5)
    sec.bottom_margin = Cm(2.5)
    return doc


def add_title_block(doc, subtitle: str):
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("AIC·智能体互联技术方案")
    set_run_font(r, east="黑体", size=18, bold=True)

    st = doc.add_paragraph()
    st.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = st.add_run(subtitle)
    set_run_font(r2, east="黑体", size=16, bold=True)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r3 = sub.add_run("作品：采联 AgentLink —— 异构采销多智能体互联协同系统")
    set_run_font(r3, size=12)

    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rn = note.add_run("（全文不出现参赛单位校名、LOGO与指导教师信息）")
    set_run_font(rn, size=10.5)
    rn.font.color.rgb = RGBColor(0x66, 0x66, 0x66)


def save_doc(doc: Document, desktop_name: str, materials_name: str):
    out2 = MATERIALS / materials_name
    out2.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out2))
    print("saved", out2)
    out = DESKTOP / desktop_name
    try:
        doc.save(str(out))
        print("saved", out)
    except PermissionError:
        alt = out.with_name(out.stem + "_新稿" + out.suffix)
        doc.save(str(alt))
        print("desktop locked; saved", alt)
