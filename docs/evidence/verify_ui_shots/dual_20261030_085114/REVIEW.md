# 双路径全链路验证 · 20261030_085114

目录：`docs/evidence/verify_ui_shots/dual_20261030_085114/`

## 普通询价全链路
- **结果**: `PASS`
- **问题**: []
```json
{
  "discover": {
    "case_id": "case-7b7f7467",
    "state": "SHORTLIST_PENDING",
    "n": 3,
    "ids": [
      "supplier-a",
      "supplier-b",
      "supplier-c"
    ],
    "source": "platform_adp"
  },
  "shortlist": {
    "case_id": "case-7b7f7467",
    "state": "SOURCING"
  },
  "rfq": {
    "case_id": "case-7b7f7467",
    "state": "COMPARE_PENDING",
    "quote_n": 1,
    "suppliers": [
      null
    ]
  },
  "order": {
    "case_id": "case-7b7f7467",
    "state": "ORDER_DRAFT",
    "supplier": "supplier-a",
    "product": "重型脚轮300kg",
    "qty": 500,
    "unit": 18.0,
    "goods": 9000.0,
    "ticket": "tk-ord-ase-7b7f7467-supplier-a-M-CASTER-300"
  },
  "ship": {
    "state": "CONTRACT_PENDING",
    "ticket": "tk-ord-ase-7b7f7467-supplier-a-M-CASTER-300"
  },
  "done": {
    "case_id": "case-7b7f7467",
    "ticket": "tk-ord-ase-7b7f7467-supplier-a-M-CASTER-300"
  },
  "sup": {
    "acked": [
      {
        "agent": "supplier-a",
        "tid": "tk-ord-ase-7b7f7467-supplier-a-M-CASTER-300",
        "effective": true
      },
      {
        "agent": "supplier-a",
        "tid": "tk-ord-ase-768aad64-supplier-a-M-CASTER-200",
        "effective": true
      }
    ],
    "logs": []
  },
  "finish": {
    "activated": [
      {
        "case": "case-7b7f7467",
        "state": "ACTIVE"
      }
    ]
  }
}
```

## 组群竞价全链路
- **结果**: `PASS`
- **问题**: []
```json
{
  "discover": {
    "case_id": "case-c4c16118",
    "state": "SHORTLIST_PENDING",
    "n": 3
  },
  "rfq": {
    "case_id": "case-c4c16118",
    "state": "COMPARE_PENDING",
    "quotes": 2
  },
  "auction": {
    "case_id": "case-c4c16118",
    "state": "BID_REVIEW",
    "transport": "group",
    "priced": 2,
    "schemes": 0,
    "best": null,
    "fallback": null,
    "abort": null,
    "bids": [
      {
        "id": "supplier-a",
        "unit": 13.5
      },
      {
        "id": "supplier-c",
        "unit": 15.0
      }
    ]
  },
  "order": {
    "case_id": "case-c4c16118",
    "state": "ORDER_DRAFT",
    "supplier": "supplier-a",
    "product": "标准脚轮200kg",
    "qty": 500,
    "goods": 6750.0,
    "ticket": "tk-ord-ase-c4c16118-supplier-a-M-CASTER-200"
  },
  "done": {
    "case_id": "case-c4c16118",
    "ticket": "tk-ord-ase-c4c16118-supplier-a-M-CASTER-200",
    "transport": "group",
    "priced": 2
  },
  "sup": {
    "acked": [
      {
        "agent": "supplier-a",
        "tid": "tk-ord-ase-c4c16118-supplier-a-M-CASTER-200",
        "effective": true
      }
    ],
    "logs": []
  },
  "finish": {
    "activated": [
      {
        "case": "case-c4c16118",
        "state": "ACTIVE"
      }
    ]
  },
  "transport": "group"
}
```

## 逐步截图

### 01. N00_home_chat（buyer-a/chat）
- ![01_N00_home_chat.png](screenshots/01_N00_home_chat.png)

### 02. N00_tickets_before（buyer-a/tickets）
- ![02_N00_tickets_before.png](screenshots/02_N00_tickets_before.png)

### 03. N01_after_order_tickets（buyer-a/tickets）
- ![03_N01_after_order_tickets.png](screenshots/03_N01_after_order_tickets.png)

### 04. N02_chat_status（buyer-a/chat）
- chat: `用表格说明采购案 case-7b7f7467：状态、候选、询价与订单关键信息。`
- ![04_N02_chat_status.png](screenshots/04_N02_chat_status.png)

### 05. N03_sa_tickets（supplier-a/tickets）
- ![05_N03_sa_tickets.png](screenshots/05_N03_sa_tickets.png)

### 06. N03_sb_tickets（supplier-b/tickets）
- ![06_N03_sb_tickets.png](screenshots/06_N03_sb_tickets.png)

### 07. N03_sc_tickets（supplier-c/tickets）
- ![07_N03_sc_tickets.png](screenshots/07_N03_sc_tickets.png)

### 08. N04_sa_after_ack（supplier-a/tickets）
- ![08_N04_sa_after_ack.png](screenshots/08_N04_sa_after_ack.png)

### 09. N05_logistics（logistics/tickets）
- ![09_N05_logistics.png](screenshots/09_N05_logistics.png)

### 10. N06_final_tickets（buyer-a/tickets）
- ![10_N06_final_tickets.png](screenshots/10_N06_final_tickets.png)

### 11. N07_audit（buyer-a/audit）
- ![11_N07_audit.png](screenshots/11_N07_audit.png)

### 12. N08_chat_final（buyer-a/chat）
- chat: `确认采购案 case-7b7f7467 是否 ACTIVE，一句话。`
- ![12_N08_chat_final.png](screenshots/12_N08_chat_final.png)

### 13. A00_before（buyer-a/chat）
- ![13_A00_before.png](screenshots/13_A00_before.png)

### 14. A01_after_auction_tickets（buyer-a/tickets）
- ![14_A01_after_auction_tickets.png](screenshots/14_A01_after_auction_tickets.png)

### 15. A02_chat_auction_summary（buyer-a/chat）
- chat: `说明采购案 case-c4c16118 竞价 transport、有效出价、中标方与订单。`
- ![15_A02_chat_auction_summary.png](screenshots/15_A02_chat_auction_summary.png)

### 16. A03_sa_tickets（supplier-a/tickets）
- ![16_A03_sa_tickets.png](screenshots/16_A03_sa_tickets.png)

### 17. A03_sc_tickets（supplier-c/tickets）
- ![17_A03_sc_tickets.png](screenshots/17_A03_sc_tickets.png)

### 18. A04_sa_after_ack（supplier-a/tickets）
- ![18_A04_sa_after_ack.png](screenshots/18_A04_sa_after_ack.png)

### 19. A05_logistics（logistics/tickets）
- ![19_A05_logistics.png](screenshots/19_A05_logistics.png)

### 20. A06_final_tickets（buyer-a/tickets）
- ![20_A06_final_tickets.png](screenshots/20_A06_final_tickets.png)

### 21. A07_audit（buyer-a/audit）
- ![21_A07_audit.png](screenshots/21_A07_audit.png)

### 22. A08_chat_final（buyer-a/chat）
- chat: `确认采购案 case-c4c16118 是否 ACTIVE，一句话。`
- ![22_A08_chat_final.png](screenshots/22_A08_chat_final.png)
