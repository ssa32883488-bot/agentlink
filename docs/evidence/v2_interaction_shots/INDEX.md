# commerce_v2 交互验收证据

- 技术现状：[`../../commerce_v2_asbuilt.md`](../../commerce_v2_asbuilt.md)
- 契约：`commerce_v2/interaction_contract.md`
- 运行时：`AGENTLINK_RUNTIME=v2`（默认）；旧 wit/flow 在 `commerce/_legacy/`
- 自动化矩阵：`tests/test_commerce_v2_interaction.py`（partner-iq / path-normal / path-group / buyer-b）
- 断点步骤导出：`scripts/run_v2_interaction_shots.py` → `docs/evidence/v2_interaction_shots/<timestamp>/`
- 双云冒烟：[`REMOTE_ACCEPT_20261030.md`](./REMOTE_ACCEPT_20261030.md)
- **UI 双路径截图（最新）**：[`../verify_ui_shots/v2_dual_20261030_194944/`](../verify_ui_shots/v2_dual_20261030_194944/) · 索引 [`../verify_ui_shots/INDEX.md`](../verify_ui_shots/INDEX.md)
