# -*- coding: utf-8 -*-
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

p = next(Path(__file__).parent.glob("*第三四章*commerce_v2*.docx"))
d = Document(str(p))
lines = []
lines.append(f"FILE {p.name}")
lines.append(f"paras={len(d.paragraphs)} tables={len(d.tables)} images={len(d.inline_shapes)}")
lines.append("---PARAS---")
for i, para in enumerate(d.paragraphs):
    t = para.text.rstrip()
    if not t.strip():
        continue
    style = para.style.name if para.style else ""
    lines.append(f"{i}|{style}|{t}")

lines.append("---TABLES---")
for ti, table in enumerate(d.tables):
    lines.append(f"TABLE {ti} rows={len(table.rows)} cols={len(table.columns)}")
    for ri, row in enumerate(table.rows):
        cells = [c.text.replace("\n", " / ").strip() for c in row.cells]
        lines.append(f"  R{ri}: " + " | ".join(cells))

out = Path(__file__).parent / "_ch34_v2_extract.txt"
out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out, "lines", len(lines))

# figure-like mentions
print("---FIGURE CANDIDATES---")
for line in lines:
    if any(k in line for k in ("图", "插图", "示意", "架构", "时序", "流程", "甘特", "【", "生成")):
        if len(line) < 220:
            print(line)
