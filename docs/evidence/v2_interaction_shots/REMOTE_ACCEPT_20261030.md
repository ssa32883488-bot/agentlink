# commerce_v2 双云验收 2026-10-30

## 部署

- 瘦包：`dist/agentlink_remote.tar.gz` ≈ 8.5MB（排除 gradle/证据大图）
- buyer（腾讯云 81.70.46.119）：8010/8012/8015 均 `AGENTLINK_RUNTIME=v2`
- supplier（阿里云 39.105.20.113）：8011/8013/8014 均 v2 Partner

## 冒烟

| 端点 | 结果 |
|------|------|
| `https://ashui.online:8010/api/erp/chat-engine` | `commerce_v2` |
| `https://ashui.online:8012/...` / `:8015/...` | buyer-b / logistics partner |
| `https://moknobita.xyz:8011/api/erp/chat-engine` | `commerce_v2_partner` |
| 公网采购一句 → 短名单 | `SHORTLIST_PENDING` + `shortlist_confirm` |
| 短名单确认 → 初报 | `BARGAIN_ASK` |

## 本地矩阵

`python tests/test_commerce_v2_interaction.py` → ALL PASS（partner-iq / path-normal / path-group / buyer-b）

## 晚间补强（同日）

| 项 | 结果 |
|----|------|
| 多品（脚轮+坐垫）改写/发现/组群按行报价 | 已修复漏项；见 `docs/commerce_v2_asbuilt.md` §4.1 |
| 国标 Group 邀请 SSL | `AIP_SSL_INSECURE`；供应 joined 验证通过 |
| UI 双路径截图 | `docs/evidence/verify_ui_shots/v2_dual_20261030_194944/`（15 图 + Word） |
| 组群聊天室「收起」 | 轮询不再强弹；可展开 |
