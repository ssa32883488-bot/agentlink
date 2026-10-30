# E2E 思考链条复盘 · 20261029_163056

## 场景对照

| 场景 | 结果 | 问题数 |
| --- | --- | --- |
| S1_combo_split | PASS | 0 |
| S2_group_auction | PASS | 0 |

## S1_combo_split

- ok: `True`
- issues: []
- shots: 15
- discover: `{"case": "case-141c0699", "n": 3, "src": "platform_adp", "ids": ["supplier-a", "supplier-b", "supplier-c"]}`
- rfq: `{"ok": true, "coverage": {"RM-CASTER-300": ["supplier-a"], "RM-FABRIC-PRO": ["supplier-b"]}, "split_plan": [{"sku": "RM-CASTER-300", "supplier_agent_id": "supplier-a", "grand_total": 9000.0, "unit_price": 18.0}, {"sku": "RM-FABRIC-PRO", "supplier_agent_id": "supplier-b", "grand_total": 17500.0, "unit_price": 35.0}], "fail": 2, "ok_n": 2}`
- core: `{"case_id": "case-141c0699", "orders": [{"sku": "RM-CASTER-300", "supplier": "supplier-a", "product": "重型脚轮300kg", "qty": 500, "goods": 9000.0, "ticket": "tk-ord-ase-141c0699-supplier-a-M-CASTER-300", "state": "CONTRACT_PENDING", "ship_state": "CONTRACT_PENDING", "title_ok": true}, {"sku": "RM-FABRIC-PRO", "supplier": "supplier-b", "product": "高档座椅面料", "qty": 500, "goods": 17500.0, "ticket": "tk-ord-ase-141c0699-supplier-b-M-FABRIC-PRO", "state": "CONTRACT_PENDING", "ship_state": "CONTRACT_PENDI`
- finish: `{"activated": [{"case": "case-141c0699", "state": "ACTIVE"}, {"case": "case-8017d8d4", "state": "ACTIVE"}, {"case": "case-a252dea0", "state": "ACTIVE"}, {"case": "case-b59b184d", "state": "ACTIVE"}, {"case": "case-3e919848", "state": "ACTIVE"}, {"case": "case-ce36ba30", "state": "ACTIVE"}, {"case": "case-d3d21e14", "state": "ACTIVE"}], "effective_orders": []}`
- supplier_ack: `{"acked": [{"agent": "supplier-a", "tid": "tk-ord-ase-d3d21e14", "title": "销售订单 · 重型脚轮300kg×500 + 高档座椅面料×200 × 700 · 买方 buyer-a · 货款 12600.0", "effective": null, "status": "supplier_acked"}, {"agent": "supplier-a", "tid": "tk-ord-ase-fba29488", "title": "销售订单 · 重型脚轮 × 500 · 买方 buyer-a · 货款 9000.0", "effective": null, "status": "supplier_acked"}, {"agent": "supplier-a", "tid": "tk-ord-ase-ce36ba30", "title": "销售订单 · 重型脚轮300kg × 300 · 买方 buyer-a · 货款 6000.0", "effective": null, "status": "supplier`

### 截图
- ![s1_01_buyer_chat_empty.png](screenshots/s1_01_buyer_chat_empty.png)
- ![s1_02_buyer_after_demand.png](screenshots/s1_02_buyer_after_demand.png)
- ![s1_03_buyer_after_shortlist_try.png](screenshots/s1_03_buyer_after_shortlist_try.png)
- ![s1_04_buyer_chat_mid.png](screenshots/s1_04_buyer_chat_mid.png)
- ![s1_05_buyer_tickets.png](screenshots/s1_05_buyer_tickets.png)
- ![s1_06_buyer_audit.png](screenshots/s1_06_buyer_audit.png)
- ![s1_07_supplier_a_tickets.png](screenshots/s1_07_supplier_a_tickets.png)
- ![s1_07_supplier_a_tickets_acked.png](screenshots/s1_07_supplier_a_tickets_acked.png)
- ![s1_08_supplier_b_tickets.png](screenshots/s1_08_supplier_b_tickets.png)
- ![s1_08_supplier_b_tickets_acked.png](screenshots/s1_08_supplier_b_tickets_acked.png)
- ![s1_09_buyer_tickets_final.png](screenshots/s1_09_buyer_tickets_final.png)
- ![s1_10_buyer_audit_final.png](screenshots/s1_10_buyer_audit_final.png)
- ![s1_11_logistics_tickets.png](screenshots/s1_11_logistics_tickets.png)
- ![s1_12_sa_final.png](screenshots/s1_12_sa_final.png)
- ![s1_13_sb_final.png](screenshots/s1_13_sb_final.png)

## S2_group_auction

- ok: `True`
- issues: []
- shots: 8
- s2_auction: `{"state": "BID_REVIEW", "transport": "group", "priced": 1, "schemes": 1, "best": {"scheme_id": "sch-supplier-a", "supplier_agent_id": "supplier-a", "aic": "1.2.156.3088.1.BUPT.2HY2P9.WP4OOG.AE0C7A.1CHP", "unit_price": 18.0, "quantity": 500, "goods_total": 9000.0, "shipping_cost": 120.0, "tco": 9120.0, "lead_time_days": 6, "eta_days": 7, "origin_city": "沧州", "dest_postal": "071000", "bid_id": "bid-98e25894", "transport": "group"}}`
- s2_order: `{"state": "ORDER_DRAFT", "supplier": "supplier-a", "unit": 18.0, "goods": 9000.0, "ship": 120.0, "ticket": "tk-ord-ase-a1617871-supplier-a-M-CASTER-300", "product": "重型脚轮300kg", "qty": 500}`
- finish: `{"activated": [{"case": "case-a1617871", "state": "ACTIVE"}], "effective_orders": []}`
- supplier_ack: `{"acked": [{"agent": "supplier-a", "tid": "tk-ord-ase-a1617871-supplier-a-M-CASTER-300", "title": "销售订单 · 重型脚轮300kg × 500 · 买方 buyer-a · 货款 9000.0", "effective": true, "status": "docs_sent"}, {"agent": "supplier-a", "tid": "tk-ord-ase-7b19fba5", "title": "销售订单 · 脚轮 × 300 · 买方 buyer-b · 货款 6000.0", "effective": null, "status": "supplier_acked"}], "logs": []}`

### 截图
- ![s2_01_chat_empty.png](screenshots/s2_01_chat_empty.png)
- ![s2_02_after_demand.png](screenshots/s2_02_after_demand.png)
- ![s2_03_after_choice_try.png](screenshots/s2_03_after_choice_try.png)
- ![s2_04_buyer_tickets.png](screenshots/s2_04_buyer_tickets.png)
- ![s2_05_buyer_audit.png](screenshots/s2_05_buyer_audit.png)
- ![s2_06_buyer_final_tickets.png](screenshots/s2_06_buyer_final_tickets.png)
- ![s2_07_logistics_tickets.png](screenshots/s2_07_logistics_tickets.png)
- ![s2_08_supplier_a_final.png](screenshots/s2_08_supplier_a_final.png)
