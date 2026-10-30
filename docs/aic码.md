# 智能体 AIC 码

> 以下为**线上证书 CN** 对齐后的运行时 AIC（2026-10-29）。  
> 环境变量必须与 `agent-cert.pem` 的 CN 一致，否则会出现 `SenderIdentityMismatchError` / `AuthorizationFailedError`。  
> 阿里云 Java 供应 HTTPS 实际读的是 `/etc/agentlink/tls/aic/<role>/server.crt`（不是仅改 env）；该文件 CN 也必须与下表一致。  
> 梧桐 ADP 仍可能返回旧 AIC；采购侧发现/询价会用本域 `SUPPLIER_*_AIC` 覆盖后再出站。

| 智能体 | AIC（证书 CN） |
| --- | --- |
| 采联采购智能体A (`buyer-a`) | `1.2.156.3088.1.BUPT.2HY2P9.IFL6BJ.MWEDJS.0GUC` |
| 采联采购智能体B (`buyer-b`) | `1.2.156.3088.1.BUPT.2HY2P9.L18AT6.DR2I98.0IWJ` |
| 采联物流智能体 (`logistics`) | `1.2.156.3088.1.BUPT.2HY2P9.JOBNF9.39B1TM.0ALR` |
| 采联供应商智能体A (`supplier-a`) | `1.2.156.3088.1.BUPT.2HY2P9.WP4OOG.AE0C7A.1CHP` |
| 采联供应商智能体B (`supplier-b`) | `1.2.156.3088.1.BUPT.2HY2P9.6CW2XR.2UXYPG.1CQG` |
| 采联供应商智能体C (`supplier-c`) | `1.2.156.3088.1.BUPT.2HY2P9.1VQMIO.SY0GFP.09NH` |
