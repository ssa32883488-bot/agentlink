# -*- coding: utf-8 -*-
import re
from pathlib import Path

t = Path(r"C:\Users\32081\Desktop\demo(1)\demo\index.html").read_text(encoding="utf-8")
# nav items roughly
for m in re.finditer(r'class="nav-item[^"]*"[^>]*>(.*?)</div>', t, re.S):
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    if text and len(text) < 40:
        print("NAV:", text)
print("--- panels ---")
for m in re.finditer(r'class="panel-tab[^"]*"[^>]*>([^<]+)', t):
    print("TAB:", m.group(1).strip())
