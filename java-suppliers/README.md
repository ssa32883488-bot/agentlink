# AgentLink Java 供应商 A/B/C

Spring Boot 3 + LangChain4j（DeepSeek OpenAI 兼容）+ 自研 AIP `/rpc` 适配层。  
金额/促销走规则引擎；议价话术可选 LLM 润色。

## 端口（与 Python 供应对齐，便于切换）

| 进程 | 端口 | AIC 默认 |
|------|------|----------|
| supplier-a | 8011 | supplier-a-local-aic |
| supplier-b | 8013 | supplier-b-local-aic |
| supplier-c | 8014 | supplier-c-local-aic |

## 构建 / 启动

需 **JDK 17+**（不要只用 JRE）。

```powershell
cd java-suppliers
.\gradlew.bat :supplier-a:bootRun
.\gradlew.bat :supplier-b:bootRun
.\gradlew.bat :supplier-c:bootRun
```

或打包：

```powershell
.\gradlew.bat bootJar
java -jar supplier-a\build\libs\supplier-a-0.1.0.jar
```

可选环境变量：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`SUPPLIER_*_AIC`。

## 冒烟

```powershell
..\..\.venv\Scripts\python.exe ..\scripts\smoke_java_suppliers.py
```
