# commerce_v2 双路径询价截图 · 20261030_194944

- UI: `https://ashui.online:8090/`
- 需求话术: `帮我采购500脚轮和400坐垫`
- 目录: `docs/evidence/verify_ui_shots/v2_dual_20261030_194944/`

## 路径说明
1. **普通询价**：发现短名单 →「确认并询价」→ 报价/决策
2. **组群竞价**：发「我要组群竞价」→ 勾选供应+物流 → 组群聊天室全量报价 → 选方案

## 运行备注
```json
{
  "normal": {
    "shortlist_clicked": true,
    "flow": "case-e9d68c39 · BARGAIN_ASK · 发现:platform_adp"
  },
  "group": {
    "group_confirm_clicked": true,
    "room_opened": true,
    "plan_clicked": true,
    "flow": "case-0789948b · GROUP_DECIDE · 发现:platform_adp"
  }
}
```

## 逐步截图与日志

### 01. N00_home
- 说明: 新建对话首页
- 截图: ![01_N00_home.png](screenshots/01_N00_home.png)
- 日志: [`logs/01_N00_home.md`](logs/01_N00_home.md) · [`logs/01_N00_home.json`](logs/01_N00_home.json)

### 02. N01_after_demand
- 输入: `帮我采购500脚轮和400坐垫`
- 说明: 发送后界面
- 案状态: `case-e9d68c39 · SHORTLIST_PENDING · 发现:platform_adp`
- 截图: ![02_N01_after_demand.png](screenshots/02_N01_after_demand.png)
- 日志: [`logs/02_N01_after_demand.md`](logs/02_N01_after_demand.md) · [`logs/02_N01_after_demand.json`](logs/02_N01_after_demand.json)

### 03. N01b_trails_expanded
- 说明: 展开处理轨迹
- 案状态: `case-e9d68c39 · SHORTLIST_PENDING · 发现:platform_adp`
- 截图: ![03_N01b_trails_expanded.png](screenshots/03_N01b_trails_expanded.png)
- 日志: [`logs/03_N01b_trails_expanded.md`](logs/03_N01b_trails_expanded.md) · [`logs/03_N01b_trails_expanded.json`](logs/03_N01b_trails_expanded.json)

### 04. N02_shortlist_confirm
- 说明: 已勾选并提交短名单/组群
- 案状态: `case-e9d68c39 · BARGAIN_ASK · 发现:platform_adp`
- 截图: ![04_N02_shortlist_confirm.png](screenshots/04_N02_shortlist_confirm.png)
- 日志: [`logs/04_N02_shortlist_confirm.md`](logs/04_N02_shortlist_confirm.md) · [`logs/04_N02_shortlist_confirm.json`](logs/04_N02_shortlist_confirm.json)

### 05. N03_decide_try
- 说明: 未找到选项: ('下单', '采纳', '最优', '确认', '继续', '订货')
- 案状态: `case-e9d68c39 · BARGAIN_ASK · 发现:platform_adp`
- 截图: ![05_N03_decide_try.png](screenshots/05_N03_decide_try.png)
- 日志: [`logs/05_N03_decide_try.md`](logs/05_N03_decide_try.md) · [`logs/05_N03_decide_try.json`](logs/05_N03_decide_try.json)

### 06. N04_normal_end
- 说明: 普通询价路径阶段结束
- 案状态: `case-e9d68c39 · BARGAIN_ASK · 发现:platform_adp`
- 截图: ![06_N04_normal_end.png](screenshots/06_N04_normal_end.png)
- 日志: [`logs/06_N04_normal_end.md`](logs/06_N04_normal_end.md) · [`logs/06_N04_normal_end.json`](logs/06_N04_normal_end.json)

### 07. G00_home
- 说明: 组群路径新建对话
- 截图: ![07_G00_home.png](screenshots/07_G00_home.png)
- 日志: [`logs/07_G00_home.md`](logs/07_G00_home.md) · [`logs/07_G00_home.json`](logs/07_G00_home.json)

### 08. G01_after_demand
- 输入: `帮我采购500脚轮和400坐垫`
- 说明: 发送后界面
- 案状态: `case-0789948b · SHORTLIST_PENDING · 发现:platform_adp`
- 截图: ![08_G01_after_demand.png](screenshots/08_G01_after_demand.png)
- 日志: [`logs/08_G01_after_demand.md`](logs/08_G01_after_demand.md) · [`logs/08_G01_after_demand.json`](logs/08_G01_after_demand.json)

### 09. G01b_trails
- 说明: 展开处理轨迹（进入组群前）
- 案状态: `case-0789948b · SHORTLIST_PENDING · 发现:platform_adp`
- 截图: ![09_G01b_trails.png](screenshots/09_G01b_trails.png)
- 日志: [`logs/09_G01b_trails.md`](logs/09_G01b_trails.md) · [`logs/09_G01b_trails.json`](logs/09_G01b_trails.json)

### 10. G02_enter_group
- 输入: `我要组群竞价`
- 说明: 发送后界面
- 案状态: `case-0789948b · GROUP_ASK · 发现:platform_adp`
- 截图: ![10_G02_enter_group.png](screenshots/10_G02_enter_group.png)
- 日志: [`logs/10_G02_enter_group.md`](logs/10_G02_enter_group.md) · [`logs/10_G02_enter_group.json`](logs/10_G02_enter_group.json)

### 11. G03_confirm_group_members
- 说明: 已勾选并提交短名单/组群
- 案状态: `case-0789948b · GROUP_DECIDE · 发现:platform_adp`
- 截图: ![11_G03_confirm_group_members.png](screenshots/11_G03_confirm_group_members.png)
- 日志: [`logs/11_G03_confirm_group_members.md`](logs/11_G03_confirm_group_members.md) · [`logs/11_G03_confirm_group_members.json`](logs/11_G03_confirm_group_members.json)

### 12. G04_group_room
- 说明: 组群聊天室已出现内容
- 案状态: `case-0789948b · GROUP_DECIDE · 发现:platform_adp`
- 截图: ![12_G04_group_room.png](screenshots/12_G04_group_room.png)
- 日志: [`logs/12_G04_group_room.md`](logs/12_G04_group_room.md) · [`logs/12_G04_group_room.json`](logs/12_G04_group_room.json)

### 13. G05_room_before_decide
- 说明: 汇总前/决策前聊天室
- 案状态: `case-0789948b · GROUP_DECIDE · 发现:platform_adp`
- 截图: ![13_G05_room_before_decide.png](screenshots/13_G05_room_before_decide.png)
- 日志: [`logs/13_G05_room_before_decide.md`](logs/13_G05_room_before_decide.md) · [`logs/13_G05_room_before_decide.json`](logs/13_G05_room_before_decide.json)

### 14. G06_pick_plan
- 说明: 点击: 全量覆盖 · 2 品拆单 · 重型脚轮300kg←supplier-a + 记忆海绵坐垫←supplier-c · 合计
- 案状态: `case-0789948b · GROUP_DECIDE · 发现:platform_adp`
- 截图: ![14_G06_pick_plan.png](screenshots/14_G06_pick_plan.png)
- 日志: [`logs/14_G06_pick_plan.md`](logs/14_G06_pick_plan.md) · [`logs/14_G06_pick_plan.json`](logs/14_G06_pick_plan.json)

### 15. G07_group_end
- 说明: 组群路径阶段结束
- 案状态: `case-0789948b · GROUP_DECIDE · 发现:platform_adp`
- 截图: ![15_G07_group_end.png](screenshots/15_G07_group_end.png)
- 日志: [`logs/15_G07_group_end.md`](logs/15_G07_group_end.md) · [`logs/15_G07_group_end.json`](logs/15_G07_group_end.json)
