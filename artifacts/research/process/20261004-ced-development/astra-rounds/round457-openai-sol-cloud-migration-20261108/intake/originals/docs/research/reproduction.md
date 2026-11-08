# 云、边、端研发复现入口

本页对应 `ced.research.v2`。逐步结果见[阶段总结](process/continuation_20261004.md)，源文件、RED/GREEN、历次补修和独立审查归档在[本轮证据目录](../../artifacts/research/process/20261004-ced-development/)。历史夹爪、模型和旧先导产物保持原版本。

## 环境与边界

从项目根目录使用现有 `.venv/bin/python`；新增原生视觉依赖声明在 `pyproject.toml` 的 `rgbd-research` 组。需要渲染的本机 MuJoCo 检查使用 `MUJOCO_GL=egl`。Dashboard 要求 Node ≥22.12，不能使用本机旧 Node 18。边缘当前是规则/成本接口，模型选择后置。

实际 Max 配置必须由本机模型管理 profile 与 secret store，或明确的 `BIGSMALL_VLM_API_KEY` 环境变量提供。配置、报告和聊天不保存密钥值。角色探针需要显式 `--allow-paid`；干运行不会自动切换旧模型。现有源绑定不能证明远端权重、端侧误差界、风险校准或研究方法准入。

## 软件回归

按修改范围运行，以下集合有重叠，不能相加作为独立测试总数：

```sh
.venv/bin/python -m pytest -q tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py tests/test_native_action_submit.py
.venv/bin/python -m pytest -q tests/test_opencv_target_evidence.py tests/test_visual_effect_evidence.py tests/test_visual_evidence_contract.py
.venv/bin/python -m pytest -q tests/test_ced_pilot_stages.py tests/test_ced_initial_freeze.py tests/test_research_pilot.py tests/test_research_protocol.py
.venv/bin/python -m pytest -q tests/test_recovery_lifecycle_module.py tests/test_retry_lifecycle_consumer.py tests/test_recovery_completion.py tests/test_replan_activation.py tests/test_visual_repair_builder.py
.venv/bin/python -m pytest -q tests/test_research_runner.py tests/test_research_statistics.py tests/test_research_results_api.py tests/test_research_reproducibility.py
MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_protocol_raw_observers.py::test_teacher_passive_hooks_cover_real_steps_and_exact_command_ranges
```

前端从 `dashboard/` 运行 `npm run test`、`npm run typecheck` 和 `npm run build`。只读证据页的实际浏览器检查入口为 `npx playwright test --config playwright.research.config.ts`，依赖 Node、项目 Python 虚拟环境和已安装的匹配 Chromium。该配置挂载实际研究 API 的隔离测试服务，使用完整 BLOCKED 软件记录；它不代表整个服务器、真实模型或物理任务验收。

## 干运行与冻结拒绝

每次使用新的输出目录，保持全部原始分配：

```sh
.venv/bin/python scripts/run_rgbd_pilot.py --stage selection --config configs/research/ced_selection.yaml --output /tmp/ced-selection-new
.venv/bin/python scripts/run_rgbd_pilot.py --stage foundation --config configs/research/ced_foundation.yaml --output /tmp/ced-foundation-new
.venv/bin/python scripts/run_rgbd_pilot.py --stage power --config configs/research/ced_foundation.yaml --output /tmp/ced-power-new
.venv/bin/python scripts/freeze_rgbd_protocol.py --stage initial --expected-protocol-version ced.research.v2 --pilot /tmp/ced-foundation-new --output /tmp/ced-initial-new
```

缺实际前置条件时退出 3：selection 保留 480 个周期分配，foundation 保留 120 个分配，power 保留 120 组且不猜测已执行方法数。INITIAL 不发布。拒绝退出是有效的保护结果，不是一次成功实验。

真实运行前必须逐项验收：当前源码/配置的新 Max 原始双图探针；端侧标定、几何/运动保守界和连续效果条件；四周期真实 selection 与独立基础先导；完整机会/故障证明；成功路径资源预算。之后才能 INITIAL、实际风险校准、共同方法冻结、独立功效先导和 FINAL。任一环节缺证据不能用 YAML 或软件 fixture 放行。

## 统计与完整原始资料

T18 复现清单记录来源文件及原始分配索引，校验完整池、协议和模型绑定后调用同一统计入口重建；不会执行清单中保存的 shell 命令。

```sh
.venv/bin/python scripts/reproduce_rgbd_research.py --bundle /path/to/bundle --output /tmp/ced-verify-new --verify-only
.venv/bin/python scripts/reproduce_rgbd_research.py --bundle /path/to/software-bundle --output /tmp/ced-numeric-new --software-only
```

第一种只验文件完整性，不证明来源真实性或物理成功。第二种数值一致仍为 `SOFTWARE_ONLY`。本轮 600 组×7 方法的 4,200 条 BLOCKED 记录用于统计、API 和浏览器复现，实际研究状态为 `NOT_RUN`，独立物理验收数量为 0。

真实研究交付还需要全部方法的实际执行和独立原始物理来源验证，不能从当前恒关闭的准入入口推导正式收益。具体尚未满足的条件见[结果与限制](results_and_limits.md)。
