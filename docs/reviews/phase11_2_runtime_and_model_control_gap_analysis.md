# Phase 11.1-R / 11.2 Gap Analysis

## 审计基线

- 审计时间：2026-06-18
- 当前分支：`main`
- 当前本地 HEAD：`d65209bc2d6a3835bbe95a2ff78476e9d94a7e9c`
- 当前 `origin/main`：`7a2464aa67629ea6942f5a9d6386740b6ea8f597`
- 计划声明的 baseline SHA：`7a2464aa67629ea6942f5a9d6386740b6ea8f597`
- 当前偏差：本地 HEAD 已包含 6 个未推送的中文注释提交，因此不满足计划中的 `HEAD == origin/main`。本分析不回滚、不 rebase、不 force push，只记录当前工作树事实。
- 工作区：审计前已提交前端中文说明批次，当前应保持 clean。

## 已检查范围

- `src/cloud_edge_robot_arm/simulation_runtime/`
- `src/cloud_edge_robot_arm/simulation_workbench/`
- `src/cloud_edge_robot_arm/cloud/planning/adapter.py`
- `src/cloud_edge_robot_arm/cloud/planning/pipeline.py`
- `src/cloud_edge_robot_arm/cloud/api/app.py`
- `src/cloud_edge_robot_arm/config.py`
- `dashboard/src/`
- `scripts/verify_phase11_1_simulation_runtime.py`
- `tests/test_phase11_1_simulation_runtime.py`
- `artifacts/phase11_1/runtime/`
- `artifacts/phase11_1/verification/`

## Phase 11.1-R：runtime evidence 缺口

### 1. terminal artifacts 落后于数据库终态

`SimulationWorker._execute()` 当前流程在成功路径中先执行：

1. `RUNNING -> FINALIZING`
2. `_write_artifacts(job, ...)`
3. `save_metrics()`
4. `save_artifacts()`
5. `append_event("artifact_created")`
6. `finish_attempt(... SUCCEEDED ...)`
7. `FINALIZING -> SUCCEEDED`

`_write_artifacts()` 使用的是进入执行时读取的旧 `job` 对象，并在终态状态转换、attempt 完成、artifact_created/job_completed 事件写入之前生成 `job.json`、`runtime_job.json`、`attempts.jsonl`、`state_transitions.jsonl` 和 `events.jsonl`。因此最终 artifact 不是终态快照。

抽样证据：`artifacts/phase11_1/runtime/sim-116b3ff15b8a/`

- `result.json`：`status=SUCCEEDED`
- `job.json`：`status=LEASED`
- `runtime_job.json`：`status=LEASED`
- `attempts.jsonl` 最后一条：`result=RUNNING` 且 `ended_at=""`
- `state_transitions.jsonl` 最后一条：`RUNNING -> FINALIZING`
- `events.jsonl` 最后一条：`job_finalizing`
- 缺少可证明终态的 `job_completed` 与终态转换快照

这说明目前 artifact 中“业务结果成功”和“runtime 作业仍运行中”并存，不能作为 Phase 11.1 runtime acceptance 的权威 evidence。

### 2. 取消、超时、失败路径也缺少统一终态 finalization

`_write_terminal_artifacts()` 在异常路径中会先 `finish_attempt()`，然后 `_write_artifacts()`，再 `save_artifacts()`、`artifact_created`、再次 `finish_attempt()`。该路径仍缺少统一的终态后重读 repository、释放 lease 后重写 evidence、一致性 manifest 和原子写入策略。

### 3. evidence 写入不是原子提交

`_write_artifacts()` 当前直接调用 `write_text()` 或 `open("w")` 覆盖权威文件。若进程在写入中断，可能留下半写入 JSON/JSONL 或部分终态文件。当前没有：

- 临时文件；
- `flush`；
- `fsync`；
- `os.replace`；
- 文件 hash manifest；
- `evidence_consistency.json`。

### 4. recovery verifier 不构成真实恢复证明

`scripts/verify_phase11_1_simulation_runtime.py` 的 `verify_recovery()` 当前直接返回：

- `restart_recovery_accepted=True`
- `lease_recovery_accepted=True`

它只调用 `service.runtime.recover()`，没有构造 stale lease、没有销毁并重建 service、没有验证 `RUNNING -> INTERRUPTED -> RECOVERY_PENDING -> QUEUED`，也没有让第二个 worker 接管。因此当前 verifier 是静态声明，不是实际恢复验收。

MuJoCo 验收中的：

- `M11-09` 只记录 `runtime.recover()` 响应；
- `M11-10` 固定写 `duplicate_execution_prevented=True`。

这不能证明服务重启恢复或双 worker 竞争只执行一次。

### 5. duplicate execution prevention 缺少实测

当前 verifier 没有同时启动 worker-A 与 worker-B 竞争同一 queued job，也没有记录：

- competing worker ids；
- lease winner；
- lease loser；
- runner invocation count；
- attempt count；
- result hash count。

因此不能证明 CAS lease 在实际竞争下防止重复执行。

## Phase 11.2：模型配置中心缺口

### 1. 模型配置仍依赖环境变量

`AppConfig` 仍通过环境变量读取：

- `PLANNER_API_ENDPOINT`
- `PLANNER_API_KEY`
- `PLANNER_MODEL`

这适合 CLI/生产启动，但不支持 Dashboard 中创建多个 profile、切换 active planner、测试连接或审计 config version。

### 2. 缺少 active planner profile

当前 `PlanningPipeline` 持有单个 planner adapter。系统没有：

- `ModelProviderProfile`；
- active profile id；
- profile version/CAS；
- endpoint hash；
- active planner runtime status；
- planner call audit 中的 profile metadata。

### 3. 缺少模型连接测试

当前 `OpenAICompatiblePlannerAdapter` 可以调用兼容 chat-completions 的端点，但没有 API：

- 测试 endpoint reachability；
- 验证鉴权；
- 验证模型存在；
- 验证响应 JSON 格式；
- 记录 latency、error_code 和 sanitized message。

### 4. 缺少本地 Ollama 管理

仓库中目前没有 `model_control` 后端模块，也没有 Ollama client。缺少能力：

- 检测 Ollama status/version；
- 列出已安装模型；
- 查看模型详情；
- 通过 HTTP API 流式 pull；
- 记录下载进度；
- 删除未使用模型；
- 激活本地模型；
- 使用 OpenAI-compatible `/v1/chat/completions` 复用 PlannerAdapter。

### 5. 缺少小模型目录

当前没有 `configs/models/small_model_catalog.yaml`，React 页面也没有动态目录来源。需要后端读取目录并返回带 `checked_at`、大小未知标记和硬件兼容性建议的列表。

### 6. 缺少一键运行的完整前端入口

当前 Dashboard 有 Vite 开发/测试流程，但没有统一的 bootstrap、start 和
model-runtime check 启动脚本：

这些入口需要在 Phase 11.2 中新增，并且必须避免自动安装 Ollama、自动下载模型
或写入 API key。

FastAPI 也尚未在生产模式挂载 `/console` SPA，同时保持 `/api/*` 和 WebSocket 优先。

## 安全风险

### 1. API key 风险

新增模型配置中心必须避免：

- API key 明文进入 SQLite；
- API key 回显到响应；
- API key 写入 localStorage；
- API key 出现在日志、artifact、OpenAPI example 或异常消息；
- Authorization header 被保存或传到前端。

需要 SecretStore 抽象，默认 session-only/in-memory，环境变量模式只保存变量名，不保存值。

### 2. SSRF / endpoint 风险

OpenAI-compatible endpoint 是用户可配置 URL，必须校验：

- scheme 仅允许 `http`/`https`；
- 云端默认要求 HTTPS；
- loopback HTTP 只用于明确允许的本地服务；
- 禁止 metadata address、link-local、本地文件、`file:`、`data:`、`javascript:`；
- DNS 解析后再校验，限制重定向和响应大小，防 DNS rebinding。

Ollama 默认只能访问 `127.0.0.1`、`localhost`、`::1`，远程 Ollama 默认关闭。

### 3. 任意下载风险

Ollama pull 只能接受模型名，不能接受任意 URL、路径、脚本或 shell 命令。下载不应写入项目目录，模型二进制由 Ollama 自己管理。

### 4. 任意命令风险

本阶段不得为了 Ollama 或 GPU 检测执行用户可控命令。允许固定参数数组调用如 `nvidia-smi`，必须 `shell=False`、timeout，并且不接收用户命令。

### 5. silent fallback 风险

云端模型或 Ollama 失败时不得自动切换 Mock/RuleBased 并声称成功。默认 fallback policy 必须是 `NONE`，任何 fallback 都必须由用户显式启用并写入 audit。

## 建议实施顺序

1. 先修 Phase 11.1-R terminal evidence：引入原子写入工具和 `SimulationArtifactFinalizer`，让终态 artifact 从 repository 终态重读生成。
2. 增加 consistency manifest 和 verifier 检查，先让现有 Mock/MuJoCo runtime evidence 不再自相矛盾。
3. 增加真实 recovery / duplicate worker 测试，替换 verifier 中的固定布尔值。
4. 新建 `model_control` 后端最小闭环：profiles、SecretStore、EndpointSecurityPolicy、PlannerFactory、fake provider tests。
5. 增加 Ollama HTTP client 与 fake Ollama 测试，不调用 shell。
6. 增加 Dashboard Model Control Center 页面和 `/api/v1/model-control/*`。
7. 增加一键启动脚本和 `/console` 静态挂载。
8. 最后补 verifier、secret scanner、docs 和 E2E。

## 当前不能直接声明的状态

当前仓库不能声明：

- `PHASE11_1_RUNTIME_EVIDENCE_ACCEPTED`
- `PHASE11_2_MODEL_CONTROL_CENTER_ACCEPTED`
- `PHASE11_2_SIMULATION_AI_CONSOLE_ACCEPTED`

原因是 runtime terminal artifacts 已实测不一致，模型控制中心后端、前端、Ollama 管理、secret 安全、endpoint 安全和一键启动入口均未实现。
