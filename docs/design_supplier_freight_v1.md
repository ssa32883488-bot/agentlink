# 供应侧 V1：被动 `discover.logistics` + 货+运回执

> 2026-10-26 落地说明

## 路径

```
采购 AIP quote_request (need_freight=true)
  → 供应商定价
  → discover.logistics（ADP；未命中则本域 LOGISTICS_RPC_URL）
  → AIP shipping_request → 物流
  → initial_quote 含 freight_amount / freight / distance_km
```

## 关键文件

| 文件 | 作用 |
|---|---|
| `commerce/discovery.py` · `discover_logistics` | 供应侧物流发现 |
| `agents/supplier_common/freight.py` | 合入运费 |
| `agents/supplier_{a,b,c}/graph.py` | async 报价管线 |
| `agentlink_runtime/partner_app.py` | 支持 await pipeline |
| `agents/logistics/policy.yaml` | 沧州/邢台/太原→保定分区 |

## 跨云注意

- 供应商在阿里云，物流在腾讯云
- 出站须配置 `AIP_CLIENT_CERT/KEY`（`/etc/agentlink/supplier-*.env`）
- `LOGISTICS_RPC_URL=https://81.70.46.119:8015/rpc`（覆盖平台 ACS 域名，避免证书链问题）
