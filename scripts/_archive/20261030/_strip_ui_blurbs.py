# -*- coding: utf-8 -*-
"""Strip instructional blurbs from ERP UI."""
from __future__ import annotations

import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = root / "ui" / "static" / "app.js"
t = p.read_text(encoding="utf-8")
nl = "\r\n" if "\r\n" in t else "\n"
t = t.replace("\r\n", "\n")

# 1) Replace page subtitle map entries to empty strings
t2, n = re.subn(
    r'(chat: \["pageChat", `\$\{who\} · 智能对话`, )`[^`]*`',
    r'\1""',
    t,
    count=1,
)
print("chat sub", n)
t = t2

# Replace all remaining map third-arg blurbs in showPage map
# peer / notify / ... one by one via generic: , "..." ] or , `...`]
def empty_map_subs(src: str) -> str:
    keys = [
        "peer",
        "notify",
        "workbench",
        "sales",
        "inventory",
        "history",
        "audit",
        "catalog",
        "inbox",
        "supAudit",
    ]
    titles = {
        "peer": "工作区",
        "notify": "通知中心",
        "workbench": "工作台",
        "sales": "销售订单",
        "inventory": "原料库存",
        "history": "对话历史",
        "audit": "任务审计",
        "catalog": "库存与价目",
        "inbox": "询价箱",
        "supAudit": "任务审计",
    }
    for k in keys:
        title = titles[k]
        page = {
            "peer": "pagePeer",
            "notify": "pageNotify",
            "workbench": "pageWorkbench",
            "sales": "pageSales",
            "inventory": "pageInventory",
            "history": "pageHistory",
            "audit": "pageAudit",
            "catalog": "pageCatalog",
            "inbox": "pageInbox",
            "supAudit": "pageSupAudit",
        }[k]
        pat = rf'{k}: \["{page}", `\$\{{who\}} · [^`]+`, (?:"[^"]*"|`[^`]*`)'
        repl = f'{k}: ["{page}", `${{who}} · {title}`, ""'
        src2, n = re.subn(pat, repl, src, count=1)
        print(k, n)
        src = src2
    return src


t = empty_map_subs(t)

# pageSub hide when empty
if '$("pageSub").classList.toggle("hidden", !sub);' not in t:
    t = t.replace(
        '$("pageSub").textContent = sub;\n    document.querySelectorAll(".nav")',
        '$("pageSub").textContent = sub;\n    $("pageSub").classList.toggle("hidden", !sub);\n    document.querySelectorAll(".nav")',
        1,
    )
    print("pageSub toggle ok")

# chatAgentTag
t2, n = re.subn(
    r'if \(\$\("chatAgentTag"\)\) \{\n'
    r'      \$\("chatAgentTag"\)\.textContent = chatBuyer\n'
    r'        \? `当前对话智能体：\$\{who\}（库 data/\$\{S\.agentId\}\.sqlite3）`\n'
    r'        : "";\n'
    r'    \}',
    'if ($("chatAgentTag")) {\n'
    '      $("chatAgentTag").textContent = "";\n'
    '      $("chatAgentTag").classList.add("hidden");\n'
    "    }",
    t,
    count=1,
)
print("chatAgentTag", n)
t = t2

# renderPeerWorkspace
t2, n = re.subn(
    r"  function renderPeerWorkspace\(\) \{.*?\n  \}\n\n  async function refreshHealth",
    "  function renderPeerWorkspace() {\n"
    "    const who = agentTitle();\n"
    '    $("peerTitle").textContent = `${who} 工作区`;\n'
    '    $("peerBody").textContent = "";\n'
    "  }\n\n  async function refreshHealth",
    t,
    count=1,
    flags=re.S,
)
print("peer", n)
t = t2

# flowCaseLabel default
t2, n = re.subn(
    r'if \(!S\.flowCaseId\) \{\n'
    r'      \$\("flowCaseLabel"\)\.textContent = "[^"]*";\n'
    r'(?:      bar\.classList\.add\("hidden"\);\n)?'
    r'      renderFlowSteps\(null\);',
    'if (!S.flowCaseId) {\n'
    '      $("flowCaseLabel").textContent = "";\n'
    '      bar.classList.add("hidden");\n'
    "      renderFlowSteps(null);",
    t,
    count=1,
)
print("flow", n)
t = t2

# welcome
t2, n = re.subn(
    r'box\.innerHTML = `<div class="msg ai"><div class="bubble">[^<]+</div></div>`;',
    'box.innerHTML = `<div class="msg ai"><div class="bubble">你好，我是${agentTitle()}助手。</div></div>`;',
    t,
    count=1,
)
print("welcome", n)
t = t2

# workbench suggestion card
t2, n = re.subn(
    r'\n      <div class="card"><strong>建议</strong><p class="muted">[^<]*</p></div>`;',
    "`;",
    t,
    count=1,
)
print("workbench", n)
t = t2

# collab empty head
t2, n = re.subn(
    r'head = `<div class="muted collab-case">尚无进行中采购案[^`]*`;',
    'head = "";',
    t,
    count=1,
)
print("collab head", n)
t = t2

t2, n = re.subn(
    r'box\.innerHTML = head \+ metricsHtml \+ `<p class="muted">暂无跨 Agent 交互记录[^`]*`;',
    'box.innerHTML = head + metricsHtml + `<p class="muted">暂无协作记录</p>`;',
    t,
    count=1,
)
print("collab empty", n)
t = t2

t2, n = re.subn(
    r'box\.innerHTML = `<p class="muted">供应侧：在询价箱查看入站 AIP</p>`;',
    'box.innerHTML = `<p class="muted">暂无记录</p>`;',
    t,
    count=1,
)
print("supplier right", n)
t = t2

t2, n = re.subn(
    r'alert\(`「\$\{agentTitle\(\)\}」没有对话工作区[^`]*`\);',
    'alert(`「${agentTitle()}」暂无对话工作区`);',
    t,
    count=1,
)
print("alert", n)
t = t2

# remove side-comment about 侧栏
t = t.replace(
    "    // 侧栏：仅对话型采购智能体显示 ERP 导航（其它智能体不共用该菜单）\n",
    "",
)

bad = [
    "不与其它智能体共用",
    "直接输入需求即可",
    "直接用自然语言告诉我",
    "用自然语言说明下一步",
    "试着在对话里说",
    "库 data/",
]
for b in bad:
    if b in t:
        print("STILL:", b)
    else:
        print("gone:", b)

p.write_text(t.replace("\n", nl), encoding="utf-8")
print("written", p)
