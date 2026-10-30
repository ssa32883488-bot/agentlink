# E2E 思考链条复盘 · 20261029_181318

## 场景对照

| 场景 | 结果 | 问题数 |
| --- | --- | --- |
| S1_combo_split | PASS | 0 |
| S2_group_auction | FAIL | 2 |

## S1_combo_split

- ok: `True`
- issues: []
- shots: 14
- discover: `{"case": "case-22b4b02c", "n": 3, "src": "platform_adp", "ids": ["supplier-a", "supplier-b", "supplier-c"]}`
- rfq: `{"ok": true, "coverage": {"RM-CASTER-300": ["supplier-a"], "RM-FABRIC-PRO": ["supplier-b"]}, "split_plan": [{"sku": "RM-CASTER-300", "supplier_agent_id": "supplier-a", "grand_total": 9000.0, "unit_price": 18.0}, {"sku": "RM-FABRIC-PRO", "supplier_agent_id": "supplier-b", "grand_total": 17500.0, "unit_price": 35.0}], "fail": 2, "ok_n": 2}`
- core: `{"case_id": "case-22b4b02c", "orders": [{"sku": "RM-CASTER-300", "supplier": "supplier-a", "product": "重型脚轮300kg", "qty": 500, "goods": 9000.0, "ticket": "tk-ord-ase-22b4b02c-supplier-a-M-CASTER-300", "state": "CONTRACT_PENDING", "ship_state": "CONTRACT_PENDING", "title_ok": true}, {"sku": "RM-FABRIC-PRO", "supplier": "supplier-b", "product": "高档座椅面料", "qty": 500, "goods": 17500.0, "ticket": "tk-ord-ase-22b4b02c-supplier-b-M-FABRIC-PRO", "state": "CONTRACT_PENDING", "ship_state": "CONTRACT_PENDI`
- finish: `{"activated": [{"case": "case-22b4b02c", "state": "ACTIVE"}], "effective_orders": [{"tid": "tk-ord-ase-22b4b02c-supplier-b-M-FABRIC-PRO", "title": "采购订单 · 高档座椅面料 × 500 · 供方 supplier-b"}, {"tid": "tk-ord-ase-22b4b02c-supplier-a-M-CASTER-300", "title": "采购订单 · 重型脚轮300kg × 500 · 供方 supplier-a"}]}`
- supplier_ack: `{"acked": [{"agent": "supplier-b", "tid": "tk-ord-ase-22b4b02c-supplier-b-M-FABRIC-PRO", "title": "销售订单 · 高档座椅面料 × 500 · 买方 buyer-a · 货款 17500.0", "effective": true, "status": "both_acked"}], "logs": []}`

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
- ![s1_09_buyer_tickets_final.png](screenshots/s1_09_buyer_tickets_final.png)
- ![s1_10_buyer_audit_final.png](screenshots/s1_10_buyer_audit_final.png)
- ![s1_11_logistics_tickets.png](screenshots/s1_11_logistics_tickets.png)
- ![s1_12_sa_final.png](screenshots/s1_12_sa_final.png)
- ![s1_13_sb_final.png](screenshots/s1_13_sb_final.png)

## S2_group_auction

- ok: `False`
- issues: ["组群竞价有效出价应≥2家（同物料多家可比）: {'state': 'BID_REVIEW', 'transport': 'group', 'priced': 0, 'schemes': 0, 'best': None}", "组群场景未生成订单工单"]
- shots: 8
- s2_auction: `{"state": "BID_REVIEW", "transport": "group", "priced": 0, "schemes": 0, "best": null}`
- finish: `{"activated": [], "effective_orders": [{"tid": "tk-ord-ase-2428006b-supplier-b-M-FABRIC-PRO", "title": "采购订单 · 高档座椅面料 × 500 · 供方 supplier-b"}, {"tid": "tk-ord-ase-2428006b-supplier-a-M-CASTER-300", "title": "采购订单 · 重型脚轮300kg × 500 · 供方 supplier-a"}, {"tid": "tk-ord-ase-22b4b02c-supplier-b-M-FABRIC-PRO", "title": "采购订单 · 高档座椅面料 × 500 · 供方 supplier-b"}, {"tid": "tk-ord-ase-22b4b02c-supplier-a-M-CASTER-300", "title": "采购订单 · 重型脚轮300kg × 500 · 供方 supplier-a"}]}`
- supplier_ack: `{"acked": [], "logs": []}`

### 截图
- ![s2_01_chat_empty.png](screenshots/s2_01_chat_empty.png)
- ![s2_02_after_demand.png](screenshots/s2_02_after_demand.png)
- ![s2_03_after_choice_try.png](screenshots/s2_03_after_choice_try.png)
- ![s2_04_buyer_tickets.png](screenshots/s2_04_buyer_tickets.png)
- ![s2_05_buyer_audit.png](screenshots/s2_05_buyer_audit.png)
- ![s2_06_buyer_final_tickets.png](screenshots/s2_06_buyer_final_tickets.png)
- ![s2_07_logistics_tickets.png](screenshots/s2_07_logistics_tickets.png)
- ![s2_08_supplier_a_final.png](screenshots/s2_08_supplier_a_final.png)
