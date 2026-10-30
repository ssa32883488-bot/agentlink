
import json, urllib.request

def chat(port, text):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/erp/chat" % port,
        data=json.dumps({"text": text}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def via_ui(ui_port, agent, text):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/proxy/%s/api/erp/chat" % (ui_port, agent),
        data=json.dumps({"text": text}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

ok = True
for agent, erp, ui in (
    ("supplier-a", 18011, 8091),
    ("supplier-b", 18013, 8093),
    ("supplier-c", 18014, 8094),
):
    o = chat(erp, "查看库存")
    reply = o.get("reply") or ""
    intent = o.get("intent")
    good = intent == "query_catalog" and "RM-" in reply and not reply.startswith("我是供应商助手")
    print(agent, "erp", "OK" if good else "BAD", intent, "lines", reply.count("RM-"))
    ok = ok and good
    u = via_ui(ui, agent, "价目")
    ugood = (u.get("intent") == "query_catalog") and ("RM-" in (u.get("reply") or ""))
    print(agent, "ui", "OK" if ugood else "BAD", u.get("intent"))
    ok = ok and ugood
print("ALL_SUPPLIERS_CHAT_PASS" if ok else "ALL_SUPPLIERS_CHAT_FAIL")
