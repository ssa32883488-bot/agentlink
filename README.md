# 采联 AgentLink

基于 **ACPs / AIP 智能体互联标准** 的工业采销协同演示：六个独立智能体跨进程互联，完成「寻源 → 询价/组群竞价 → 下单确认 → 物流」闭环。

仓库地址：<https://github.com/ssa32883488-bot/agentlink>

当前默认业务运行时为 **`commerce_v2`**（`AGENTLINK_RUNTIME=v2`）：

- **普通询价路径**：需求改写 → ADP 发现 → 短名单确认 → 初报/议价 → 下单 Gate → 物流  
- **组群竞价路径**：采购主持开群 → 按行出价 → 全量覆盖方案 → 拆单确认  

人机断点：**AskUser**（选题推进）与 **Gate**（工单 ack 产生效力）分离。

---

## 架构一览

| 智能体 | API 端口 | 本地 UI | 角色 |
|--------|----------|---------|------|
| 采购商 A | 8010 | 8090 | Leader；双路径编排；组群主持 |
| 供应商 A | 8011 | 8091 | 结构件（如脚轮） |
| 采购商 B | 8012 | 8092 | 第二采购租户 |
| 供应商 B | 8013 | 8093 | 面料 / 坐垫 |
| 供应商 C | 8014 | 8094 | 多品类 / 替代 |
| 物流 | 8015 | 8095 | 运力方案 |
| 座椅商城 | — | 8080 | C 端下单演示（可选） |

本地默认 **HTTP**；双云正式环境使用 HTTPS + 平台证书（见下文「接梧桐平台」）。

```
人机 UI (809x) ──► 采购/供应/物流 Agent (80xx)
                         │
              commerce_v2 编排 + Partner 信封
                         │
         ACPs：AIC / ACS / ADP / AIP / Group / AMP
                         │
              （可选）梧桐 Registry / Discovery / Kafka
```

---

## 环境要求

- **Python 3.12+**（推荐；或安装 [uv](https://github.com/astral-sh/uv)）
- Windows 10/11（PowerShell）或 Linux / macOS（bash）
- 可访问外网：安装 pip 依赖；调用 LLM API
- **自备 LLM API Key**（OpenAI 兼容，推荐 [DeepSeek](https://platform.deepseek.com/)）

发布压缩包已内置：

- `vendor/acps-sdk`（ACPs SDK）
- `vendor/wit_framework-*.whl`（Wit 运行时，平台入驻等场景使用）

---

## 一键本地部署（推荐）

### 方式 A：GitHub 克隆

```powershell
git clone https://github.com/ssa32883488-bot/agentlink.git
cd agentlink
.\scripts\bootstrap_local.ps1
```

Linux / macOS：

```bash
git clone https://github.com/ssa32883488-bot/agentlink.git
cd agentlink
chmod +x scripts/*.sh
./scripts/bootstrap_local.sh
```

> 若仓库尚未包含 `vendor/`，请使用下方「发布压缩包」，或自行将 `acps-sdk` 与 Wit wheel 放入 `vendor/`。

### 方式 B：发布压缩包

1. 解压 `agentlink_local_deploy_*.zip`
2. 阅读根目录 `START_HERE.txt`
3. 执行引导脚本（同上）

### 配置 API Key

引导脚本会从 `.env.example` 生成 `.env`。**必填**：

```env
LLM_API_KEY=sk-你的密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
AGENTLINK_RUNTIME=v2
AIP_IDENTITY_BINDING=0
AMP_KAFKA_ENABLED=0
```

不要把含真实 Key 的 `.env` 提交到 Git。

### 启动

```powershell
.\scripts\start_all_local.ps1
.\scripts\start_ui_local.ps1
```

```bash
./scripts/start_all_local.sh
./scripts/start_ui_local.sh
```

浏览器打开：**http://127.0.0.1:8090**（采购商 A）

停止：

```powershell
.\scripts\stop_all_local.ps1
```

### 冒烟验证

```powershell
.\.venv\Scripts\python.exe scripts\smoke_all_local.py
```

期望输出含 `SMOKE_ALL_OK`。

---

## 目录说明（上传 / 发布包含什么）

| 路径 | 说明 |
|------|------|
| `agents/` | 六智能体 FastAPI 入口 |
| `commerce_v2/` | **当前主路径**编排、Partner、交互契约 |
| `commerce/` | 共享库、种子数据；`_legacy/` 为旧 Wit/组群适配 |
| `agentlink_runtime/` | AIP RPC / Partner 公共运行时 |
| `ui/` | 控制台与商城；`ui/local/` 为本地 HTTP 配置 |
| `acs/` | 各体 ACS 描述 JSON |
| `config/` | 平台配置示例（不含密钥） |
| `vendor/` | 内置 acps-sdk + wit wheel |
| `scripts/bootstrap_*` / `start_*` / `stop_*` | 一键引导与启停 |
| `docs/commerce_v2_asbuilt.md` | 技术现状 |
| `java-suppliers/` | 可选 Java Partner 样例（不含 Gradle 发行包） |

**不会进入 Git / 发布包的内容**（见 `.gitignore`）：

- `.env`、证书私钥、`certs/platform/`
- `.venv/`、`data/*.sqlite*`、`logs/`、`dist/`
- 证据截图、大体积 docx/pptx、远程 hotfix 脚本、双云私有 env

自行打包：

```powershell
.\scripts\pack_release.ps1
```

产物：`release/agentlink_local_deploy_*.zip`

---

## 演示怎么玩

1. 打开采购商 A：http://127.0.0.1:8090  
2. 输入多品需求，例如：需要脚轮 200 个、记忆棉坐垫 150 套  
3. **普通路径**：短名单 →「确认并询价」→ 按提示议价/买法 → 工单 Gate 确认  
4. **组群路径**：选「我要组群竞价」→ 勾选供应（±物流）→ 在组群聊天室看按行报价 → 选全量覆盖方案  

技术细节：`docs/commerce_v2_asbuilt.md`、`commerce_v2/interaction_contract.md`。

---

## 接梧桐平台（可选）

本地演示不强制平台。正式链：

1. 填写 `.env` 中 `ACPS_*` / `AMP_*`  
2. `copy config\acps_platform.example.yaml config\acps_platform.yaml` 并改地址  
3. 入驻发证后配置 mTLS，`AIP_IDENTITY_BINDING=1`，`AMP_KAFKA_ENABLED=1`  
4. ACS 见 `acs/*.acs.json`  

双云生产拓扑与端口以 `docs/commerce_v2_asbuilt.md` 为准。

---

## 常见问题

**Q: 没有 LLM Key 能跑吗？**  
A: 进程可启动，需求改写与智能对话不可用。请至少配置 `LLM_API_KEY`。

**Q: UI 提示网络错误 / 连不上 Agent？**  
A: 确认已 `start_all_local`；本地请用 `start_ui_local`（HTTP）。不要用指向 HTTPS 的生产 `ui/config_*.yaml`。

**Q: 组群失败？**  
A: 本地默认未接平台 MQ。组群国标通道需配置 `ACPS_MQ_*`；业务可降级但不得伪称 `transport=group`。

**Q: Wit / acps-sdk 从哪来？**  
A: 发布包与完整仓库的 `vendor/`。开发机也可对照 `pyproject.toml` 的 `[tool.uv.sources]`。

---

## 开发与测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

关键模块：`commerce_v2/buyer_path_normal.py`、`buyer_path_group.py`、`protocol_bridge.py`。

---

## 许可证与致谢

- 业务代码：随本仓库分发（参赛/演示用途）  
- `vendor/acps-sdk`：遵循其自带 LICENSE（木兰 / MulanPSL 等，见包内文件）  
- 梧桐智能体科研平台：<https://wt.ioa.pub>

---

## 快速命令备忘

| 动作 | Windows | Linux/macOS |
|------|---------|-------------|
| 引导 | `.\scripts\bootstrap_local.ps1` | `./scripts/bootstrap_local.sh` |
| 启 Agent | `.\scripts\start_all_local.ps1` | `./scripts/start_all_local.sh` |
| 启 UI | `.\scripts\start_ui_local.ps1` | `./scripts/start_ui_local.sh` |
| 停止 | `.\scripts\stop_all_local.ps1` | `./scripts/stop_all_local.sh` |
| 打包 | `.\scripts\pack_release.ps1` | — |
