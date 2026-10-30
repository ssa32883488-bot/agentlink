# 继续迭代结果（协议硬门槛）· 2026-10-26 午间

## 结论

**供应商 C 已改为平台 ADP 命中**（不再依赖本地容灾）；**买卖双侧 AMP 3/3 对账通过**。

| 检查项 | 结果 |
|---|---|
| ADP `source` | **`platform_adp`**（`degrade=false`） |
| A/B/C 均 `source_label=平台发现` | **是** |
| RFQ quotes | **3** |
| buyer Message send | **3**，`messageId=msg-{taskId}` |
| supplier receive 同 taskId | **`AMP_BILATERAL_PASS`（3/3）** |
| 证据文件 | `docs/evidence/latest_pair.json` · `docs/evidence/bilateral_assert.json` |

case：`case-f681cd6c`

---

## 根因与修复（C 偶发本地兜底）

**根因**：发现逻辑在命中任意供应商（常为 A/B）后提前 `break`，后续 `scarce-quote` / 「库存紧张」查询未执行，C 只能被本地 ACS 补齐。

**修复**（`commerce/discovery.py`）：
1. 仅当 **supplier-a/b/c 三家齐** 才停止查询  
2. 补充可命中 C 的兜底词：`库存紧张 供应商`、`substitute scarce`、`采联供应商智能体C`  
3. 候选入库即 `_normalize_supplier_id`

---

## 明日演示建议

1. 对话「开始采购并发现」→ 右侧应显示 **平台 · platform_adp**（无黄色容灾）  
2. 「确认三家并询价」→ 时间线三条 Leader→供应  
3. 佐证截图优先用本轮证据（纯平台三家）  
4. 仍须补：**梧桐后台访问量截图**（人工）

复跑：
```bash
# buyer
.venv/bin/python scripts/demo_acps_evidence.py
# 本地
py -3 scripts/_assert_amp_bilateral.py
```
