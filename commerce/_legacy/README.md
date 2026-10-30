# commerce `_legacy` 归档

以下模块在「六体双路径大爆炸」中从业务入口切断，仅保留供 `AGENTLINK_RUNTIME=legacy` 回退：

- `chat_*_wit.py` / `chat_buyer.py` — DeepSeek Wit 对话编排
- `flow_routes.py` / `flow_service.py` — 旧采购案流
- `goal_runtime.py` / `hitl_*` / `scheme_planner.py` — 目标机与 HITL
- `group_mq.py` / `group_routes.py` / `auction_suitability.py` — 旧组群竞价

新路径：`commerce_v2/`（AskUser + Gate + 普通十点 + 组群主持）。
