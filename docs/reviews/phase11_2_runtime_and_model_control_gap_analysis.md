# Phase 11.1-R / 11.2 Runtime and Model Control Gap Analysis

## 审计基线

- 审计时间：2026-06-19
- 当前分支：`main`
- 当前本地 HEAD：`6f8f0c13f2c96d3a9e1f14954bb195fe8f100906`
- 当前 `origin/main`：`f9a29222d31627bfa21d7ea793eebc3c55dc3183`
- 计划声明 baseline SHA：`7a2464aa67629ea6942f5a9d6386740b6ea8f597`
- 当前偏差：本地分支已领先远端，且包含中文说明审计提交；不 rebase、不 force push、不回滚已提交历史。
- 安全边界：`real_controller_contacted=false`、`hardware_motion_observed=false`、`hardware_write_operations=[]`，本阶段不接触真实控制器。

## 已审计范围

- `src/cloud_edge_robot_arm/simulation_runtime/`
- `src/cloud_edge_robot_arm/simulation_workbench/`
- `src/cloud_edge_robot_arm/model_control/`
- `src/cloud_edge_robot_arm/cloud/api/model_control.py`
- `src/cloud_edge_robot_arm/cloud/planning/adapter.py`
- `src/cloud_edge_robot_arm/cloud/api/app.py`
- `src/cloud_edge_robot_arm/cloud/api/console_app.py`
- `dashboard/src/modelControl/`
- `scripts/verify_phase11_1_simulation_runtime.py`
- `scripts/verify_phase11_2_model_control.py`
- `tests/test_phase11_1_simulation_runtime.py`
- `tests/test_phase11_2_model_control_backend.py`

## Phase 11.1-R 运行时证据状态

### 已修复

- terminal artifact 已改为终态后从 repository 重读生成。
- 成功、取消、超时和失败路径都会生成 `evidence_consistency.json`。
- 终态 evidence 使用临时文件、flush、fsync 和 `os.replace` 原子写入。
- `verify_phase11_1_simulation_runtime.py --ci` 已构造真实 stale lease recovery。
- recovery 验证覆盖 `RUNNING -> INTERRUPTED -> RECOVERY_PENDING -> QUEUED`。
- duplicate worker competition 已实测两个 worker 竞争同一 QUEUED job，runner invocation count 为 1。
- 新增取消竞态回归：当 API 先完成 `RUNNING -> CANCEL_REQUESTED` 时，worker 会继续推进到 `CANCELLING -> CANCELLED`，不会卡在中间态。

### 当前剩余风险

- MuJoCo `--full` 仍依赖本机 MuJoCo 环境；普通 CI 不能把 fake/mock 结果声明为 MuJoCo runtime accepted。
- Playwright webServer 使用固定端口；多个 verifier 并发运行会互相污染，因此验收必须顺序执行。
- Vite 仍报告 antd/echarts 大 chunk 警告；已有 route-level lazy loading 和 manual chunks，该警告记录为非阻塞技术债。

## Phase 11.2 模型控制中心状态

### 已实现

- `ModelProviderProfile` 支持 `MOCK`、`RULE_BASED`、`OPENAI_COMPATIBLE`、`OLLAMA`。
- API key 为 write-only；响应、SQLite、artifact 和前端缓存均不返回明文 secret。
- `InMemorySecretStore` 为默认 session-only secret store。
- `EndpointSecurityPolicy` 拒绝不安全 scheme、metadata address、link-local 和默认远程 Ollama。
- `/api/v1/model-control/profiles` 支持 CRUD、active profile 切换和版本检查。
- `/api/v1/model-control/profiles/{profile_id}/test` 已支持脱敏连接测试。
- `/api/v1/model-control/runtime` 和 `/runtime/reload` 返回 active planner 运行状态。
- Ollama 管理 API 已支持 status、models、model detail、delete、download、download detail、cancel 和 activate。
- Ollama 管理只通过 HTTP API，不调用 `ollama` CLI，不使用 `shell=True`。
- `/api/v1/model-control/planner/dry-run` 明确 `dispatch=false`、`hardware_execution=false`。
- `/api/v1/model-control/stream` 提供脱敏 heartbeat，预留 replay/进度事件扩展边界。
- Dashboard 已新增 AI 模型控制中心页面，包含 profile 表单、连接测试、Ollama 状态、模型目录、下载中心和 dry-run。
- `scripts/start_bigsmall_console.py` 可挂载 `/console`，且默认 loopback；`0.0.0.0` 未配置 token 时拒绝启动。

### 当前剩余风险

- OpenAI-compatible provider 的真实云端连接测试只能在用户提供 endpoint/API key 时运行；CI 使用 fake/本地测试，不访问收费 API。
- 真实 Ollama daemon 和真实模型测试为可选验收；默认 `--ci` 使用 fake Ollama，不自动下载大型模型。
- 下载取消是 best-effort：关闭/取消当前记录，不声称删除已下载 layer。
- 小模型目录使用权威 tag 作为建议入口；未知下载大小保持 `None` 并在前端显示“大小未知”。

## 安全结论

- API key 不进入 SQLite 明文字段。
- 前端 API key 输入为 password 字段，提交后不回显，不写 localStorage。
- Ollama 下载只接受模型名，不接受 URL、路径、脚本或 shell。
- 浏览器没有真实机器人执行入口。
- 模型控制中心和仿真工作台均保持 `real_controller_contacted=false`、`hardware_motion_observed=false`、`hardware_write_operations=[]`。

## 验证计划

顺序执行，禁止并发运行两个 Playwright/verifier：

1. `python -m pytest -q tests/test_phase11_1_simulation_runtime.py tests/test_phase11_2_model_control_backend.py`
2. `cd dashboard && npm run api:check && npm run format:check && npm run lint && npm run typecheck && npm run test && npm run build && npm run e2e`
3. `python scripts/check_model_control_secrets.py`
4. `python scripts/verify_phase11_1_simulation_runtime.py --ci`
5. `python scripts/verify_phase11_2_model_control.py --ci`

只有上述验证全部通过，才能声明：

- `PHASE11_1_RUNTIME_EVIDENCE_ACCEPTED`
- `PHASE11_2_MODEL_CONTROL_CENTER_ACCEPTED`
- `PHASE11_2_SIMULATION_AI_CONSOLE_ACCEPTED`
