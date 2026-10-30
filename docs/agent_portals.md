# 六智能体独立 ERP / 控制台门户名单

> 已取消「域聚合页」；每个智能体单独控制台、单独进程、单独业务库。  
> 采购商 A / B：**同一套技术架构**（Wit 对话 + ERP + 采购案流），仅 `agent_id` 与数据不同。

## 门户一览

| 智能体 | 角色 | API（AIP/HTTP） | 独立控制台 UI | 业务库 |
|---|---|---|---|---|
| 采购商A | Leader | `https://ashui.online:8010` | **https://ashui.online:8090/** | `data/buyer-a.sqlite3` |
| 采购商B | Leader | `https://ashui.online:8012` | **https://ashui.online:8092/** | `data/buyer-b.sqlite3` |
| 物流 | Partner | `https://ashui.online:8015` | **https://ashui.online:8095/** | （Partner 侧日志/任务） |
| 供应商A | Partner | `https://39.105.20.113:8011` | **http://39.105.20.113:8091/** | `data/supplier-a.sqlite3` |
| 供应商B | Partner | `https://39.105.20.113:8013` | **http://39.105.20.113:8093/** | `data/supplier-b.sqlite3` |
| 供应商C | Partner | `https://39.105.20.113:8014` | **http://39.105.20.113:8094/** | `data/supplier-c.sqlite3` |

## 部署主机

| 云 | 主机 | 承载 |
|---|---|---|
| 腾讯云 | `ashui.online` / `81.70.46.119` | 采购A/B、物流 + 其 UI |
| 阿里云 | `39.105.20.113` | 供应商A/B/C（AIP HTTPS）+ 控制台 UI（HTTP，便于 IP 直开） |

## 说明

- 智能体之间只通过 **ADP 发现 / AIP 任务** 协作，不共享业务库。  
- 采购案文件按智能体隔离：`data/procurement_cases_buyer-a.json` / `…_buyer-b.json`。  
- 旧聚合配置 `config_buyer_domain.yaml` / `config_supplier_domain.yaml` 仅保留兼容，不再作为默认入口。
