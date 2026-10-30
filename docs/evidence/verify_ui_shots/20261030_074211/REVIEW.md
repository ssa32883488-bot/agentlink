# 普通采购 + 组群竞价 UI 验证 · 20261030_074211

证据目录：`docs/evidence/verify_ui_shots/20261030_074211/`

## 普通采购（发现→短名单→RFQ→下单→物流→激活）
- **结果**: `PASS`
- **问题**: []
- **关键数据**:
```json
{
  "discover": {
    "case_id": "case-d92099ed",
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
    "case_id": "case-d92099ed",
    "state": "SOURCING",
    "shortlist": [
      {
        "agent_id": "supplier-a",
        "aic": "1.2.156.3088.1.BUPT.2HY2P9.WP4OOG.AE0C7A.1CHP",
        "name": "采联供应商智能体A",
        "description": "沧州五金结构件供应智能体，代表沧州组件厂（河北省沧州市运河区渤海路56号，邮编061000）。承接座椅零部件询价与报价，主打价格竞争力与脚轮大批量优惠（RM-CASTER-300/200 单品满500件该单品总价九折），并可应询价方要求向物流侧询运。主营：扶手组件、五星脚底座、气压棒、重型/标准脚轮、钢管制件椅架。挂牌价按目录与公开促销结算，无私下底价通道。拒绝：窥探他方报价、无授权承诺真实发货结算、处理非本厂目录SKU。",
        "endpoint": "https://39.105.20.113:8011/rpc",
        "skills": [
          "agentlink.supplier.quote",
          "agentlink.supplier.promotions",
          "agentlink.supplier.inventory-leadtime",
          "agentlink.supplier.negotiate",
          "agentlink.supplier.freight-inquire",
          "agentlink.supplier.fulfillment"
        ],
        "source": "platform_adp",
        "acs": {
          "name": "采联供应商智能体A",
          "aic": "1.2.156.3088.1.BUPT.2HY2P9.WP4OOG.AE0C7A.1CHP",
          "version": "1.0.0",
          "_matched_skill": "agentlink.supplier.promotions"
        },
        "source_label": "平台发现",
        "degrade": false
      },
      {
        "agent_id": "supplier-b",
        "aic": "1.2.156.3088.1.BUPT.2HY2P9.6CW2XR.2UXYPG.1CQG",
        "name": "采联供应商智能体B",
        "description": "邢台软装供应智能体，代表邢台软装厂（河北省邢台市襄都区中兴路120号，邮编054000）。承接座椅面料与海绵的定制化询价报价，强调品质等定制字段与起订量约束（面料MOQ50、海绵MOQ20）；任意软装组合货价满10000减1000。主营：高档/普通座椅面料、记忆/普通海绵坐垫。低于起订量拒报或引导改量。拒绝：无定制要素的无效询价、私下底价、窥探他方报价。",
        "endpoint": "https://39.105.20.113:8013/rpc",
        "skills": [
          "agentlink.supplier.moq-validate",
          "agentlink.supplier.quote",
          "agentlink.supplier.promotions",
          "agentlink.supplier.inventory-leadtime",
          "agentlink.supplier.negotiate",
          "agentlink.supplier.freight-inquire",
          "agentlink.supplier.fulfillment"
        ],
        "source": "platform_adp",
        "acs": {
          "name": "采联供应商智能体B",
          "aic": "1.2.156.3088.1.BUPT.2HY2P9.6CW2XR.2UXYPG.1CQG",
          "version": "1.0.0",
          "_matched_skill": "agentlink.supplier.quote"
        },
        "source_label": "平台发现",
        "degrade": false
      },
      {
        "agent_id": "supplier-c",
        "aic": "1.2.156.3088.1.BUPT.2HY2P9.1VQMIO.SY0GFP.09NH",
       
```

## 组群竞价（发现→RFQ→auction→TCO下单→物流→激活）
- **结果**: `FAIL`
- **问题**: ["transport 非 group: rpc"]
- **关键数据**:
```json
{
  "discover": {
    "case_id": "case-e1919275",
    "state": "SHORTLIST_PENDING",
    "n": 3,
    "ids": [
      "supplier-a",
      "supplier-b",
      "supplier-c"
    ]
  },
  "rfq": {
    "case_id": "case-e1919275",
    "state": "COMPARE_PENDING",
    "quotes": 2
  },
  "auction": {
    "case_id": "case-e1919275",
    "state": "BID_REVIEW",
    "transport": "rpc",
    "priced": 2,
    "schemes": 0,
    "best": null,
    "bids": [
      {
        "id": "supplier-a",
        "unit": 15.0,
        "tco": null
      },
      {
        "id": "supplier-b",
        "unit": null,
        "tco": null
      },
      {
        "id": "supplier-c",
        "unit": 15.0,
        "tco": null
      }
    ]
  },
  "order": {
    "case_id": "case-e1919275",
    "state": "ORDER_DRAFT",
    "supplier": "supplier-a",
    "product": "标准脚轮200kg",
    "qty": 500,
    "goods": 6750.0,
    "ship": null,
    "ticket": "tk-ord-ase-e1919275-supplier-a-M-CASTER-200"
  },
  "done": {
    "case_id": "case-e1919275",
    "ticket": "tk-ord-ase-e1919275-supplier-a-M-CASTER-200",
    "priced": 2,
    "transport": "rpc"
  },
  "sup": {
    "acked": [
      {
        "agent": "supplier-a",
        "tid": "tk-ord-ase-e1919275-supplier-a-M-CASTER-200",
        "effective": true,
        "title": "销售订单 · 标准脚轮200kg × 500 · 买方 buyer-a · 货款 6750.0"
      }
    ],
    "logs": []
  },
  "finish": {
    "activated": [
      {
        "case": "case-e1919275",
        "state": "ACTIVE"
      }
    ]
  }
}
```

## 逐步截图

### 01. N00_buyer_home_chat（buyer-a/chat）
- ![01_N00_buyer_home_chat.png](screenshots/01_N00_buyer_home_chat.png)

### 02. N00_buyer_tickets_before（buyer-a/tickets）
- ![02_N00_buyer_tickets_before.png](screenshots/02_N00_buyer_tickets_before.png)

### 03. N01_after_discover_chat（buyer-a/chat）
- ![03_N01_after_discover_chat.png](screenshots/03_N01_after_discover_chat.png)

### 04. N01_after_discover_tickets（buyer-a/tickets）
- ![04_N01_after_discover_tickets.png](screenshots/04_N01_after_discover_tickets.png)

### 05. N02_chat_status_after_discover（buyer-a/chat）
- chat: 查看采购案 case-d92099ed 的状态与候选供应商列表，用表格说明。
- ![05_N02_chat_status_after_discover.png](screenshots/05_N02_chat_status_after_discover.png)

### 06. N03_after_rfq_chat（buyer-a/chat）
- ![06_N03_after_rfq_chat.png](screenshots/06_N03_after_rfq_chat.png)

### 07. N04_chat_compare_quotes（buyer-a/chat）
- chat: 针对采购案 case-d92099ed，汇总三家询价结果，比较单价与总价，给出推荐。
- ![07_N04_chat_compare_quotes.png](screenshots/07_N04_chat_compare_quotes.png)

### 08. N05_sa_tickets_after_rfq（supplier-a/tickets）
- ![08_N05_sa_tickets_after_rfq.png](screenshots/08_N05_sa_tickets_after_rfq.png)

### 09. N05_sb_tickets_after_rfq（supplier-b/tickets）
- ![09_N05_sb_tickets_after_rfq.png](screenshots/09_N05_sb_tickets_after_rfq.png)

### 10. N05_sc_tickets_after_rfq（supplier-c/tickets）
- ![10_N05_sc_tickets_after_rfq.png](screenshots/10_N05_sc_tickets_after_rfq.png)

### 11. N06_buyer_tickets_after_order（buyer-a/tickets）
- ![11_N06_buyer_tickets_after_order.png](screenshots/11_N06_buyer_tickets_after_order.png)

### 12. N07_sa_tickets_after_order（supplier-a/tickets）
- ![12_N07_sa_tickets_after_order.png](screenshots/12_N07_sa_tickets_after_order.png)

### 13. N08_chat_order_status（buyer-a/chat）
- chat: 查看采购案 case-d92099ed 的订单草案与物流缺口，说明下一步需谁确认。
- ![13_N08_chat_order_status.png](screenshots/13_N08_chat_order_status.png)

### 14. N09_sa_after_ack（supplier-a/tickets）
- ![14_N09_sa_after_ack.png](screenshots/14_N09_sa_after_ack.png)

### 15. N10_logistics_after_sup_ack（logistics/tickets）
- ![15_N10_logistics_after_sup_ack.png](screenshots/15_N10_logistics_after_sup_ack.png)

### 16. N11_buyer_final_tickets（buyer-a/tickets）
- ![16_N11_buyer_final_tickets.png](screenshots/16_N11_buyer_final_tickets.png)

### 17. N12_buyer_audit（buyer-a/audit）
- ![17_N12_buyer_audit.png](screenshots/17_N12_buyer_audit.png)

### 18. N13_logistics_final（logistics/tickets）
- ![18_N13_logistics_final.png](screenshots/18_N13_logistics_final.png)

### 19. N14_chat_final（buyer-a/chat）
- chat: 确认采购案 case-d92099ed 是否已激活，用一句话结论。
- ![19_N14_chat_final.png](screenshots/19_N14_chat_final.png)

### 20. A00_buyer_before_auction（buyer-a/chat）
- ![20_A00_buyer_before_auction.png](screenshots/20_A00_buyer_before_auction.png)

### 21. A01_buyer_tickets_after_auction（buyer-a/tickets）
- ![21_A01_buyer_tickets_after_auction.png](screenshots/21_A01_buyer_tickets_after_auction.png)

### 22. A02_chat_auction_summary（buyer-a/chat）
- chat: 说明采购案 case-e1919275 组群竞价的运输方式、有效出价数、最优 TCO 与中标供应方。
- ![22_A02_chat_auction_summary.png](screenshots/22_A02_chat_auction_summary.png)

### 23. A03_sa_tickets（supplier-a/tickets）
- ![23_A03_sa_tickets.png](screenshots/23_A03_sa_tickets.png)

### 24. A03_sb_tickets（supplier-b/tickets）
- ![24_A03_sb_tickets.png](screenshots/24_A03_sb_tickets.png)

### 25. A03_sc_tickets（supplier-c/tickets）
- ![25_A03_sc_tickets.png](screenshots/25_A03_sc_tickets.png)

### 26. A04_sa_after_ack（supplier-a/tickets）
- ![26_A04_sa_after_ack.png](screenshots/26_A04_sa_after_ack.png)

### 27. A05_logistics（logistics/tickets）
- ![27_A05_logistics.png](screenshots/27_A05_logistics.png)

### 28. A06_buyer_final（buyer-a/tickets）
- ![28_A06_buyer_final.png](screenshots/28_A06_buyer_final.png)

### 29. A07_buyer_audit（buyer-a/audit）
- ![29_A07_buyer_audit.png](screenshots/29_A07_buyer_audit.png)

### 30. A08_chat_final（buyer-a/chat）
- chat: 确认采购案 case-e1919275 组群竞价是否已激活，一句话结论。
- ![30_A08_chat_final.png](screenshots/30_A08_chat_final.png)
