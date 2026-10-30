from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "ui" / "static" / "app.js"
t = p.read_text(encoding="utf-8")
n0 = t.count("buyer-a")
t = t.replace('proxy("buyer-a"', "proxy(S.agentId")
t = re.sub(r"/api/agents/buyer-a/interactions", "/api/agents/${S.agentId}/interactions", t)
p.write_text(t, encoding="utf-8")
print("buyer-a before", n0, "after", t.count("buyer-a"))
