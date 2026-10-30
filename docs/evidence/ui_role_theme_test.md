# 三端换肤 · 白话测试记录

**日期**：2026-10-27  
**测什么**：采购 / 供应 / 物流三个控制台能不能一眼看出来不一样，标题够不够大。  
**怎么测**：把最新静态页推到云上，用接口看标题，用浏览器拉首页 HTML/CSS，再让旁观者 LLM 对照设计说明挑刺。

## 测试步骤（人话）

1. 把 `styles.css`、`app.js`、`index.html` 和六个 `config_*.yaml` 推到腾讯云、阿里云。  
2. 重启各 UI 服务（buyer-a/b、logistics、supplier-a/b/c）。  
3. 分别问三个域的 `/api/domain`：标题是不是「采联 / 供应 / 物流」这套说法。  
4. 打开三个首页，看有没有 `roleChip`，CSS 里有没有 `role-buyer` / `role-supplier` / `role-logistics`，标题字号有没有 `1.45rem`。  
5. 旁观者对照设计文档，给结论。

## 自动化实测结果

- **结论：PASS（部署冒烟 6/6；线上复核 9/9）**
- 脚本：`scripts/_smoke_ui_role_theme.py`、`scripts/_verify_ui_theme_live.py`
- 服务状态：腾讯云 UI（buyer-a/b、logistics）均为 `active`；阿里云 UI（supplier-a/b/c）均为 `active`
- 静态资源哈希一致（三端 CSS 同为 `eee586f57506`）

| 检查项 | 结果 |
|--------|------|
| 采购商 domain 标题 | `采购商A · 采联控制台` ✓ |
| 物流 domain 标题 | `物流智运 · 物流控制台` ✓ |
| 供应商 domain 标题 | `供应商A · 供应控制台` ✓ |
| 首页含 roleChip | ✓（采购 / 供应） |
| CSS 含三角色 class + 大标题 1.45rem | ✓ |
| JS 含 applyRoleTheme / resolveUiRole | ✓ |

## 旁观者 LLM 监控

- **过程**：只读对照 `styles.css` / `app.js` / `index.html` / 设计文档 / 本测试记录  
- **设计 vs 代码**：顶栏色轨、Logo 放大、角色徽章、主色变量与设计一致  
- **判定**：**PASS_WITH_ISSUES**（不阻断上线）  
- **残留风险（白话）**：
  1. 对话区、商城按钮等少数地方还写死了蓝色，滚到深层页面后三端差异会弱一点  
  2. 页面刚打开、角色还没从接口读回来的一瞬间，可能先闪一下默认采购蓝  
  3. 看页面请强制刷新（Ctrl+F5），免得浏览器还在用旧皮肤

## 怎么自己肉眼看

| 页面 | 地址 | 应该看到 |
|------|------|----------|
| 采购商A | https://ashui.online:8090/ | 蓝调顶条 +「采购商」徽章 + 大标题 |
| 供应商A | https://39.105.20.113:8091/ | 青绿顶条 +「供应商」徽章（证书可能告警，可继续访问） |
| 物流 | https://ashui.online:8095/ | 琥珀顶条 +「物流」徽章 |

刷新请强制刷新（Ctrl+F5），避免旧 CSS 缓存。
