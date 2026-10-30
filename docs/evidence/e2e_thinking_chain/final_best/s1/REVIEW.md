# Fast E2E · 20261029_183158

## S1_combo_split
- ok: `True`
- issues: []
- data: `{"discover": {"case": "case-825b6d1c", "n": 3, "ids": ["supplier-a", "supplier-b", "supplier-c"]}, "rfq": {"ok": true, "coverage": {"RM-CASTER-300": ["supplier-a"], "RM-FABRIC-PRO": ["supplier-b"]}, "split_plan": [{"sku": "RM-CASTER-300", "supplier_agent_id": "supplier-a", "grand_total": 9000.0, "unit_price": 18.0}, {"sku": "RM-FABRIC-PRO", "supplier_agent_id": "supplier-b", "grand_total": 17500.0, "unit_price": 35.0}], "ok_n": 2}, "done": {"case_id": "case-825b6d1c", "orders": [{"sku": "RM-CASTER-300", "supplier": "supplier-a", "product": "重型脚轮300kg", "qty": 500, "goods": 9000.0, "ticket": "tk-ord-ase-825b6d1c-supplier-a-M-CASTER-300", "bad_title": false, "state": "CONTRACT_PENDING"}, {"sku": "RM-FABRIC-PRO", "supplier": "supplier-b", "product": "高档座椅面料", "qty": 500, "goods": 17500.0, "ticket": "tk-ord-ase-825b6d1c-supplier-b-M-FABRIC-PRO", "bad_title": false, "state": "CONTRACT_PENDING`

### shots
- ![s1_buyer_tickets.png](screenshots/s1_buyer_tickets.png)
- ![s1_sa_tickets.png](screenshots/s1_sa_tickets.png)
- ![s1_sb_tickets.png](screenshots/s1_sb_tickets.png)
- ![s1_buyer_final.png](screenshots/s1_buyer_final.png)
- ![s1_logistics.png](screenshots/s1_logistics.png)
- ![s1_buyer_audit.png](screenshots/s1_buyer_audit.png)

## S2_group_auction
- ok: `False`
- issues: ["竞价有效出价应≥2: {'state': 'BID_REVIEW', 'transport': 'group', 'priced': 0, 'schemes': 0, 'best': None}", "未生成订单工单"]
- data: `{"auction": {"state": "BID_REVIEW", "transport": "group", "priced": 0, "schemes": 0, "best": null}, "sup": {"acked": [], "logs": []}, "finish": {"activated": []}}`

### shots
- ![s2_buyer_tickets.png](screenshots/s2_buyer_tickets.png)
- ![s2_sa_tickets.png](screenshots/s2_sa_tickets.png)
- ![s2_buyer_final.png](screenshots/s2_buyer_final.png)
- ![s2_logistics.png](screenshots/s2_logistics.png)
- ![s2_buyer_audit.png](screenshots/s2_buyer_audit.png)
