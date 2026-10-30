# Group P0 冒烟证据

**日期**：2026-10-27  
**结论**：PASS（同进程 + 跨云 RPC 邀请）

## 配置要点

- Broker：`wt.ioa.pub:5671`，**vhost=`acps`**（`/` 会 Connection.Close）
- ACL：`https://wt.ioa.pub/mq-auth`
- SSL：系统 CA + 平台 trust-bundle + agent 证书
- Group identity binding：`ACPS_GROUP_IDENTITY_BINDING=1`（与阿里云 `AIP_IDENTITY_BINDING=0` 解耦；否则供应回执无 AMQP `user_id`，采购侧丢弃）

## 本地同进程

```text
.\.venv\Scripts\python.exe scripts\_smoke_group_p0_local.py
→ PASS: 三供+物流 joined + ping acks
```

## 跨云 RPC（生产路径）

```text
Leader POST /api/erp/group/open → invite https://{supplier}/group/join + logistics
→ ping → 四家 Accepted→Working→AwaitingCompletion→Completed
scripts\_smoke_group_p0_rpc.py → PASS
```

## API

- `POST /api/erp/group/open`
- `POST /api/erp/group/{session_id}/ping`
- `POST /api/erp/group/{session_id}/dissolve`
- Partner：`POST /group/join`
