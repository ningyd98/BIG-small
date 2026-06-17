# Phase 5 回顾审查

## 1. 审查结论

**有条件通过**

Phase 0-5 的实现已经通过仓库质量门禁，以及历史 Phase 3、3.1、3.2、4、5 验证脚本。本次审查发现并修复了 Phase 5 的几类可靠性缺口：API 暴露不完整、supervision 状态未持久化、并发版本推进没有持久 CAS、生产配置边界不够严、文档状态过期。

剩余条件属于部署面，不是隐藏的代码绕过：MQTT transport、真实生产调度器接线、真实机械臂 SDK 接线和网络 ACK transport 仍属于部署或下一阶段边界，不能被描述成已完成的生产能力。

## 2. 仓库基线

- 审查时间：`2026-06-13T17:24:09+08:00`
- 分支：`main`
- 审查基线 SHA：`4054835d7b3175a534dc55b63ac58a3fff5a4fcc`
- Phase 5 SHA：`4054835d7b3175a534dc55b63ac58a3fff5a4fcc`
- 审查后 SHA：包含本报告的最终 commit
- 初始 Git 状态：tracked file 干净；未跟踪的 `.mimocode/` 保留
- 命令基线：shell `PATH` 上没有 `python`、`ruff` 和 `mypy`；项目门禁通过 `.venv/bin/*` 运行

## 3. 实际架构

初始规划链路：

```text
API request
  -> PlanningRequest / InitialPlanningRequest
  -> scene sufficiency check
  -> PlannerAdapter
  -> JSON parse
  -> TaskContract schema validation
  -> semantic validation and bounded repair
  -> trusted field overwrite
  -> optional InProcessEdgeGateway dispatch
  -> TaskExecutor
  -> SafetySkillExecutor
  -> SafetyShield pre/post checks
```

周期监督链路：

```text
EdgeStatusSnapshot
  -> FastAPI status/supervise endpoint
  -> SupervisionRepository snapshot persistence
  -> PeriodicSupervisorService validation
  -> DeterministicSupervisionPolicy
  -> optional PlanningPipeline replan
  -> completed-step preserving merge
  -> SupervisionRepository CAS version update
  -> SupervisoryDecision persistence
  -> audit
```

安全执行链路：

```text
TaskContract
  -> EdgeContractValidator
  -> Repository.accept_command
  -> TaskStateMachine
  -> SafetyContextBuilder
  -> SafetyShield pre_check
  -> SkillExecutor / RobotAdapter
  -> SafetyShield post_check
  -> Repository audit
```

## 4. 问题汇总

| ID | 级别 | 模块 | 问题 | 根因 | 状态 |
| --- | --- | --- | --- | --- | --- |
| R01 | P1 | 质量门禁 | 基线下 `ruff format --check` 和 `ruff check` 失败 | Phase 5 代码提交前没有强制样式门禁 | 已修复 |
| R02 | P1 | Cloud API | 必需的 supervision endpoint 缺失 | Phase 5 service 没接入 FastAPI | 已修复 |
| R03 | P1 | Supervision 持久化 | decision 和 status 只存在进程内存 | 没有 supervision repository | 已修复 |
| R04 | P1 | Supervision 并发 | 版本推进没有持久 CAS | 状态只用进程内字段 | 已修复 |
| R05 | P1 | Replanning | 已完成步骤可能被 planner 重写 | 更新路径直接使用 planner contract steps | 已修复 |
| R06 | P1 | Planner 失败路径 | replan 失败有审计，但没有显式 fail-closed 回归测试 | 缺少对抗性回归测试 | 已修复 |
| R07 | P2 | 运行配置 | 生产默认值可能落到 test/local 值 | `AppConfig.from_env` 对所有 profile 提供安全测试默认值 | 已修复 |
| R08 | P2 | API 能力文档 | planning API 把 Phase 6 `EVENT_TRIGGERED_EDGE_AUTONOMY` 宣称为支持 | 预留 enum 泄漏到已实现 capability endpoint | 已修复 |
| R09 | P2 | CI/scripts | 常规门禁漏跑 `verify_phase5.py` | CI 和本地脚本停在 Phase 4/3.2 | 已修复 |
| R10 | P2 | 文档 | Phase 5 报告宣称了过期测试/lint 状态和无条件 Phase 6 readiness | 实现缺口发现后文档未同步 | 已修复 |
| R11 | P2 | 数值边界 | Pose 接受非有限坐标 | Pose 没有 finite-number validator | 已修复 |

数量统计：

- P0：0
- P1：6，均已修复
- P2：5，均已修复
- P3：本次未单独跟踪

## 5. P0/P1 细节

- R01：基线 `ruff format --check .` 报告 5 个文件需要格式化；`ruff check .` 报告 37 个 lint error。已通过格式化、清理 import、移除 dead code 和拆分长行修复。
- R02：`src/cloud_edge_robot_arm/cloud/api/app.py` 原本只有 planning route。已新增 supervision capability、robot status intake、manual supervise、decision list、start、stop 和 status endpoint。
- R03/R04：`PeriodicSupervisorService` 只把 decision 存在 `_state.decisions`。已新增 `InMemorySupervisionRepository`、`SQLiteSupervisionRepository`，并通过 `advance_version_if_current` 提供 CAS。
- R05：supervision 更新 contract 时保留当前 contract 的已完成步骤，只合并未完成 planned step。
- R06：新增使用 `BrokenPlannerAdapter` 的 malformed planner 回归测试；replanning 失败时 `resulting_plan_version` 不变，且不产生 `updated_steps`。

## 6. 安全审查

- PathCollision：真实 3D line-segment obstacle check 仍然启用；回归测试确认路径受阻时返回 `REJECT/PATH_COLLISION`。
- Acceleration：使用真实请求加速度，并记录 measured/limit；回归测试确认 measured 非零且 limit 来自配置。
- ALLOW_WITH_LIMITS：现有集成 velocity-limit 测试仍确认受限参数被执行。
- Pre-check/post-check：`SafetySkillExecutor` 仍在机器人动作前运行 pre-check，并在动作成功后运行 post-check。
- Emergency stop：现有 Phase 3 脚本继续验证 emergency stop 和 watchdog 行为。
- Edge authority：dispatch 仍经过 `TaskExecutor` 和 `SafetyShield`；云端 contract 不会直接执行。

## 7. Planner 审查

- `MockPlannerAdapter` 仍然是确定性的测试专用 adapter，并受配置边界限制。
- `RuleBasedPlannerAdapter` 仍在 planning pipeline 和 validation chain 后面。
- `OpenAICompatiblePlannerAdapter` 仍要求 endpoint 和 API key；没有引入默认生产 API key。
- malformed planner output、禁止的低层字段、可信字段覆盖、repair limit 和 edge dispatch safety 仍由 Phase 4 测试覆盖。
- supervision replanning 现在由可信 service 代码覆盖 plan metadata，并保留已完成步骤。

## 8. Supervision 审查

- KEEP：稳定重复 snapshot 返回 KEEP，不调用 planner。
- UPDATE：目标移动会通过 repository CAS 更新 version/command sequence。
- REPLACE：与 UPDATE 共享 repository/version 机制；已完成步骤保留机制阻止已结束步骤被重写。
- PAUSE/REQUEST_MORE_OBSERVATION/ABORT：现有策略分支仍由 Phase 5 测试覆盖。
- TTL/version/idempotency：edge command acceptance 仍由 edge repository 强制；supervision decision 现在会持久化 idempotency hash。
- Duplicate snapshot：回归测试确认重复 snapshot 复用已持久化 decision，不创建第二条 decision。
- Concurrency：repository CAS 回归测试确认同一个 `(plan_version, command_seq)` 只能被一个 update 推进。
- Network degradation：现有 Phase 5 测试确认未知风险配置下会 pause。

## 9. 测试有效性

新增 `tests/test_phase5_retrospective_hardening.py`，覆盖：

- SQLite supervision persistence across repository restart
- SQLite updated-contract persistence across repository restart
- CAS version update conflict
- FastAPI supervision closed loop
- robot_id path mismatch rejection
- implemented control-mode capability boundary
- production config fail-fast
- Pose NaN/Infinity rejection
- CI/local script Phase 5 verification enforcement
- completed-step preserving update merge
- malformed planner fail-closed behavior
- duplicate snapshot idempotency

历史 `verify_phase5.py` 仍然有效，并在错误时以非零状态退出。它验证 KEEP、planner call count、update trigger、stale state rejection、PathCollision 和 Acceleration。

## 10. 命令证据

基线证据：

- `python --version`：exit 127，`command not found`
- `ruff format --check .`：exit 127，`command not found`
- `ruff check .`：exit 127，`command not found`
- `mypy src/`：exit 127，`command not found`
- `.venv/bin/ruff format --check .`：exit 1，5 个文件需要格式化
- `.venv/bin/ruff check .`：exit 1，37 个 error
- `.venv/bin/mypy src/`：exit 0
- `.venv/bin/pytest -q`：exit 0，`195 passed`

最终证据：

- `.venv/bin/ruff format --check .`：exit 0，`126 files already formatted`
- `.venv/bin/ruff check .`：exit 0，`All checks passed!`
- `.venv/bin/mypy src/`：exit 0，`Success: no issues found in 70 source files`
- `.venv/bin/pytest -q`：exit 0，`207 passed`
- `.venv/bin/python scripts/verify_phase3.py`：exit 0，`success=true`
- `.venv/bin/python scripts/verify_phase3_1.py`：exit 0，`success=true`
- `.venv/bin/python scripts/verify_phase3_2.py`：exit 0，`success=true`
- `.venv/bin/python scripts/verify_phase4.py`：exit 0，`PASS: Phase 4 acceptance suite passed`
- `.venv/bin/python scripts/verify_phase5.py`：exit 0，`PASS: Phase 5 acceptance suite passed`
- `.venv/bin/python -m compileall src`：exit 0
- `.venv/bin/python -m pip check`：exit 0，`No broken requirements found.`
- `.venv/bin/pytest --cov=src --cov-report=term-missing`：exit 4，因为当前 venv 没有安装 `pytest-cov`

## 11. 变更文件

- Cloud API：`src/cloud_edge_robot_arm/cloud/api/app.py`、`src/cloud_edge_robot_arm/cloud/api/schemas.py`
- Supervision：`src/cloud_edge_robot_arm/cloud/supervision/repository.py`、`service.py`、`core.py`、`models.py`、`__init__.py`
- Config/contracts：`src/cloud_edge_robot_arm/config.py`、`src/cloud_edge_robot_arm/contracts/models.py`
- Tests/scripts/CI：`tests/test_phase5_retrospective_hardening.py`、Phase 5 tests、verification scripts、`.github/workflows/ci.yml`、`scripts/run_checks.sh`
- Docs：README、architecture、gap analysis、Phase 5 report、本审查

## 12. 剩余已知限制

- MQTT transport 未实现。
- 生产 scheduler implementation 被声明为必需配置，但本仓库未提供。
- 未提供真实 `RobotAdapter`、`TelemetryProvider` 和 `SceneStateProvider` 实现。
- `CommandAck` 已有 model/status 支持和 edge rejection 行为，但真正的网络 ACK transport 仍是部署/传输层任务。
- 未安装 `pytest-cov`；本次审查不把 coverage 作为通过/失败标准。

## 13. Git

- commit message：`refactor: complete phase 0-5 retrospective audit and reliability hardening`
- commit SHA：创建 commit 后补充
- push：push 后补充

## 14. Phase 6 进入条件

**有条件可以进入。**

Phase 6 只能在当前门禁保持绿色后开始，并且必须明确把 event-triggered edge autonomy 当成新工作。它不能把 Mock/Fake/InMemory 实现复用为生产 fallback，也必须保留边缘侧最终执行、拒绝和 safe-stop 权限。
