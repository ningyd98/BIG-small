# 云、边、端研发复现入口

本页对应 `ced.research.v2`。逐步结果见[阶段总结](process/continuation_20261004.md)，源文件、RED/GREEN、历次补修和独立审查归档在[本轮证据目录](../../artifacts/research/process/20261004-ced-development/)。历史夹爪、模型和旧先导产物保持原版本。

## 环境与边界

从项目根目录使用现有 `.venv/bin/python`；新增原生视觉依赖声明在 `pyproject.toml` 的 `rgbd-research` 组。需要渲染的本机 MuJoCo 检查使用 `MUJOCO_GL=egl`。Dashboard 要求 Node ≥22.12，不能使用本机旧 Node 18。边缘当前是规则/成本接口，模型选择后置。

2026-11-08 按用户要求，当前云端角色改为 OpenAI 官方 API 的精确模型 `gpt-6.1-sol`。历史 Qwen 配置与实验保留原日期、模型身份和源码证据；边缘模型选择仍后置，端侧 OpenCV、可见姿态标记、顶视相机及控制器方案不变。模型接口依据见[官方模型页](https://developers.openai.com/api/docs/models/gpt-6.1-sol)和[迁移指南](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.1-sol)。当前双图 JSON 规划不使用工具调用，继续采用 Chat Completions。

实际配置由本机模型管理 profile 与 secret store，或明确的环境变量提供。配置、报告和聊天不保存密钥值。角色探针需要显式 `--allow-paid`；干运行不会自动切换旧模型。现有源绑定不能证明远端权重、端侧误差界、风险校准或研究方法准入。

### SOL 本地配置

在模型管理中单独配置新 profile，保留旧 Qwen profile。非敏感字段如下；本轮代码交付不会创建、激活或修改运行数据库中的 profile。

| 字段 | 值 |
| --- | --- |
| provider_kind | `OPENAI_COMPATIBLE` |
| model_name | `gpt-6.1-sol` |
| base_url | `https://api.openai.com` |
| chat_completions_path | `/v1/chat/completions` |
| max_tokens | `4096` |
| timeout_seconds | `180` |

SOL 的 profile `max_tokens` 会映射为实际请求的 `max_completion_tokens`，包含推理和可见输出。默认 `reasoning_effort=low`，快照可明确登记 `low/medium/high/xhigh/max`；本项目预算限制为 1–32768 个令牌。实际请求不发送 `temperature`、`max_tokens` 或 Qwen 的 `enable_thinking`。官方地址校验和禁止重定向适用于 SOL 视觉请求；配置填妥不代表账号权限、响应质量或双图能力已经通过真实验证。

密钥只在用户本地设置。角色探针可读取本地 `OPENAI_API_KEY`，运行时显式选择 `--secret-env OPENAI_API_KEY`；不指定时仍读取 `BIGSMALL_VLM_API_KEY`。Web 模型管理的 SecretStore 为会话内存，服务重启后需要重新配置。若密钥曾出现在聊天或公开记录中，请撤销并在本地更换；不要把新值加入配置、日志或 Git。

环境方式的普通交互入口另用以下设置（这不会激活研究 profile，也不授予付费调用权限）：

```sh
unset BIGSMALL_VLM_FROZEN_DIR
export BIGSMALL_VLM_PROVIDER=openai_compatible
export BIGSMALL_VLM_MODEL=gpt-6.1-sol
export BIGSMALL_VLM_BASE_URL=https://api.openai.com/v1
```

该入口的密钥变量仍是 `BIGSMALL_VLM_API_KEY`，不会自动复制 `OPENAI_API_KEY`。它使用默认 `/chat/completions` 路径，和上述带 `/v1` 的 base URL 组合；研究 profile 使用表中的另一种完整组合。`.env.example` 中已有生效的旧 `BIGSMALL_VLM_FROZEN_DIR`，该变量优先于环境模型选择，选择 SOL 环境入口时须移除该设置，避免后续加载环境文件又恢复旧冻结模型。此入口默认低推理投入和 4096 预算，不生成研究冻结证据。

`configs/research/ced_roles.yaml` 保持 `profile_id: null`，由运行入口显式选新 profile。角色探针与先导入口会核对配置家族，当前 SOL 配置配旧 Qwen profile 会在渲染及模型请求前拒绝。真实探针的 `--execute` 会启动渲染和网络调用，本轮未执行。新的模型和源码使旧 R439 source generation 与协议不适用于新运行；旧冻结字节不改写，后续需重新登记当前来源、限定付费调用预算并完成真实双图探针及独立校准。R450 的 GPU 服务操作授权仍是独立前置。软件测试通过不改变正式研究 `NOT_ACCEPTED`。

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

真实运行前必须逐项验收：当前源码/配置的新 SOL 原始双图探针；端侧标定、几何/运动保守界和连续效果条件；四周期真实 selection 与独立基础先导；完整机会/故障证明；成功路径资源预算。之后才能 INITIAL、实际风险校准、共同方法冻结、独立功效先导和 FINAL。任一环节缺证据不能用 YAML 或软件 fixture 放行。

## 统计与完整原始资料

T18 复现清单记录来源文件及原始分配索引，校验完整池、协议和模型绑定后调用同一统计入口重建；不会执行清单中保存的 shell 命令。

```sh
.venv/bin/python scripts/reproduce_rgbd_research.py --bundle /path/to/bundle --output /tmp/ced-verify-new --verify-only
.venv/bin/python scripts/reproduce_rgbd_research.py --bundle /path/to/software-bundle --output /tmp/ced-numeric-new --software-only
```

第一种只验文件完整性，不证明来源真实性或物理成功。第二种数值一致仍为 `SOFTWARE_ONLY`。本轮 600 组×7 方法的 4,200 条 BLOCKED 记录用于统计、API 和浏览器复现，实际研究状态为 `NOT_RUN`，独立物理验收数量为 0。

真实研究交付还需要全部方法的实际执行和独立原始物理来源验证，不能从当前恒关闭的准入入口推导正式收益。具体尚未满足的条件见[结果与限制](results_and_limits.md)。
