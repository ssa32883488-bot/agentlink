# 对话驱动双路径验证 · 20261030_110903

目录：`docs/evidence/verify_ui_shots/chat_dual_20261030_110903/`

## 两条具体问题
1. **普通询价**：`我打算购买 500 套重型脚轮300kg，请发现供应商并报价。先给出候选，再统一询价；我确认后再下单。`
2. **组群竞价**：`单物料复杂采购：标准脚轮200kg、数量500（多家目录都有）。请发现多家供应商后统一询价；若多家都能供且可比，请走组群竞价+TCO，再选最优方案下单。`

## 普通询价全链路
- **结果**: `PASS`
- **入口话术**: `我打算购买 500 套重型脚轮300kg，请发现供应商并报价。先给出候选，再统一询价；我确认后再下单。`
- **问题**: []
```json
{
  "discover": {
    "case_id": "case-49fd43fa",
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
    "case_id": "case-49fd43fa",
    "state": "SOURCING"
  },
  "rfq": {
    "case_id": "case-49fd43fa",
    "state": "COMPARE_PENDING",
    "quote_n": 1,
    "suppliers": [
      null
    ]
  },
  "order": {
    "case_id": "case-49fd43fa",
    "state": "ORDER_DRAFT",
    "supplier": "supplier-a",
    "product": "重型脚轮300kg",
    "qty": 500,
    "unit": 18.0,
    "goods": 9000.0,
    "ticket": "tk-ord-ase-49fd43fa-supplier-a-M-CASTER-300"
  },
  "ship": {
    "state": "CONTRACT_PENDING",
    "ticket": "tk-ord-ase-49fd43fa-supplier-a-M-CASTER-300"
  },
  "done": {
    "case_id": "case-49fd43fa",
    "ticket": "tk-ord-ase-49fd43fa-supplier-a-M-CASTER-300"
  },
  "sup": {
    "acked": [
      {
        "agent": "supplier-a",
        "tid": "tk-ord-ase-49fd43fa-supplier-a-M-CASTER-300",
        "effective": true
      }
    ],
    "logs": []
  },
  "finish": {
    "activated": [
      {
        "case": "case-49fd43fa",
        "state": "ACTIVE"
      }
    ]
  }
}
```

## 组群竞价全链路
- **结果**: `PASS`
- **入口话术**: `单物料复杂采购：标准脚轮200kg、数量500（多家目录都有）。请发现多家供应商后统一询价；若多家都能供且可比，请走组群竞价+TCO，再选最优方案下单。`
- **问题**: []
```json
{
  "discover": {
    "case_id": "case-5f036b22",
    "state": "SHORTLIST_PENDING",
    "n": 2
  },
  "rfq": {
    "case_id": "case-5f036b22",
    "state": "COMPARE_PENDING",
    "quotes": 2
  },
  "auction": {
    "case_id": "case-5f036b22",
    "state": "BID_REVIEW",
    "transport": "rpc",
    "priced": 2,
    "schemes": 0,
    "best": null,
    "fallback": true,
    "abort": "insufficient_joined_suppliers",
    "bids": [
      {
        "id": "supplier-a",
        "unit": 15.0
      },
      {
        "id": "supplier-c",
        "unit": 15.0
      }
    ]
  },
  "order": {
    "case_id": "case-5f036b22",
    "state": "ORDER_DRAFT",
    "supplier": "supplier-a",
    "product": "标准脚轮200kg",
    "qty": 500,
    "goods": 6750.0,
    "ticket": "tk-ord-ase-5f036b22-supplier-a-M-CASTER-200"
  },
  "done": {
    "case_id": "case-5f036b22",
    "ticket": "tk-ord-ase-5f036b22-supplier-a-M-CASTER-200",
    "transport": "rpc",
    "priced": 2
  },
  "sup": {
    "acked": [
      {
        "agent": "supplier-a",
        "tid": "tk-ord-ase-5f036b22-supplier-a-M-CASTER-200",
        "effective": true
      }
    ],
    "logs": []
  },
  "finish": {
    "activated": [
      {
        "case": "case-5f036b22",
        "state": "ACTIVE"
      }
    ]
  },
  "transport": "rpc"
}
```

## 逐步截图（含提问原文）

### 01. N00_empty_chat（buyer-a/chat)
- 说明: 新线程空对话
- ![01_N00_empty_chat.png](screenshots/01_N00_empty_chat.png)

### 02. N01_ask_normal_rfq（buyer-a/chat)
- 提问/对话: `我打算购买 500 套重型脚轮300kg，请发现供应商并报价。先给出候选，再统一询价；我确认后再下单。`
- 说明: 用户提问后助手回复
- ![02_N01_ask_normal_rfq.png](screenshots/02_N01_ask_normal_rfq.png)

### 03. N02_shortlist_try（buyer-a/chat)
- 说明: 已勾选短名单并提交
- ![03_N02_shortlist_try.png](screenshots/03_N02_shortlist_try.png)

### 04. N03_choice_try（buyer-a/chat)
- 说明: 未找到选项: ('询价', '报价', '继续', '确认')
- ![04_N03_choice_try.png](screenshots/04_N03_choice_try.png)

### 05. N04_chat_status_after_core（buyer-a/chat)
- 提问/对话: `刚才那条采购需求已推进，请用表格说明采购案 case-49fd43fa：状态、候选、询价与订单关键信息。`
- 说明: 用户提问后助手回复
- ![05_N04_chat_status_after_core.png](screenshots/05_N04_chat_status_after_core.png)

### 06. N05_buyer_tickets（buyer-a/tickets)
- ![06_N05_buyer_tickets.png](screenshots/06_N05_buyer_tickets.png)

### 07. N06_sa_tickets（supplier-a/tickets)
- ![07_N06_sa_tickets.png](screenshots/07_N06_sa_tickets.png)

### 08. N06_sb_tickets（supplier-b/tickets)
- ![08_N06_sb_tickets.png](screenshots/08_N06_sb_tickets.png)

### 09. N06_sc_tickets（supplier-c/tickets)
- ![09_N06_sc_tickets.png](screenshots/09_N06_sc_tickets.png)

### 10. N07_sa_after_ack（supplier-a/tickets)
- ![10_N07_sa_after_ack.png](screenshots/10_N07_sa_after_ack.png)

### 11. N08_logistics（logistics/tickets)
- ![11_N08_logistics.png](screenshots/11_N08_logistics.png)

### 12. N09_final_tickets（buyer-a/tickets)
- ![12_N09_final_tickets.png](screenshots/12_N09_final_tickets.png)

### 13. N10_audit（buyer-a/audit)
- ![13_N10_audit.png](screenshots/13_N10_audit.png)

### 14. N11_chat_final（buyer-a/chat)
- 提问/对话: `确认采购案 case-49fd43fa 是否 ACTIVE，一句话。`
- 说明: 用户提问后助手回复
- ![14_N11_chat_final.png](screenshots/14_N11_chat_final.png)

### 15. A00_empty_chat（buyer-a/chat)
- 说明: 新线程空对话
- ![15_A00_empty_chat.png](screenshots/15_A00_empty_chat.png)

### 16. A01_ask_group_auction（buyer-a/chat)
- 提问/对话: `单物料复杂采购：标准脚轮200kg、数量500（多家目录都有）。请发现多家供应商后统一询价；若多家都能供且可比，请走组群竞价+TCO，再选最优方案下单。`
- 说明: 用户提问后助手回复
- ![16_A01_ask_group_auction.png](screenshots/16_A01_ask_group_auction.png)

### 17. A02_shortlist_try（buyer-a/chat)
- 说明: 已勾选短名单并提交
- ![17_A02_shortlist_try.png](screenshots/17_A02_shortlist_try.png)

### 18. A03_choice_auction（buyer-a/chat)
- 说明: 点击选项: 发起组群竞价（推荐）
- ![18_A03_choice_auction.png](screenshots/18_A03_choice_auction.png)

### 19. A04_chat_auction_summary（buyer-a/chat)
- 提问/对话: `说明采购案 case-5f036b22 竞价 transport、有效出价、中标方与订单。`
- 说明: 用户提问后助手回复
- ![19_A04_chat_auction_summary.png](screenshots/19_A04_chat_auction_summary.png)

### 20. A05_buyer_tickets（buyer-a/tickets)
- ![20_A05_buyer_tickets.png](screenshots/20_A05_buyer_tickets.png)

### 21. A06_sa_tickets（supplier-a/tickets)
- ![21_A06_sa_tickets.png](screenshots/21_A06_sa_tickets.png)

### 22. A06_sc_tickets（supplier-c/tickets)
- ![22_A06_sc_tickets.png](screenshots/22_A06_sc_tickets.png)

### 23. A07_sa_after_ack（supplier-a/tickets)
- ![23_A07_sa_after_ack.png](screenshots/23_A07_sa_after_ack.png)

### 24. A08_logistics（logistics/tickets)
- ![24_A08_logistics.png](screenshots/24_A08_logistics.png)

### 25. A09_final_tickets（buyer-a/tickets)
- ![25_A09_final_tickets.png](screenshots/25_A09_final_tickets.png)

### 26. A10_audit（buyer-a/audit)
- ![26_A10_audit.png](screenshots/26_A10_audit.png)

### 27. A11_chat_final（buyer-a/chat)
- 提问/对话: `确认采购案 case-5f036b22 是否 ACTIVE，一句话。`
- 说明: 用户提问后助手回复
- ![27_A11_chat_final.png](screenshots/27_A11_chat_final.png)
