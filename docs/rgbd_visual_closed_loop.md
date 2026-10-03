# RGB-D Visual Closed Loop

本文说明 T7 的采集、视觉规划、同 episode 物理闭环与独立数据作业入口。默认草稿使用 `input_mode=RGBD`、`execution_scope=VISUAL_PLANNING`、`job_type=SIMULATION`。只有显式选择 `VISION_CLOSED_LOOP` 才会执行视觉驱动的机器人任务。

当前实现面向 MuJoCo 研究环境，不连接真实机械臂。截至2026-10-04，`smoke-20-v2` 已执行并通过开发 smoke 独立复算：2/20 成功、18 失败、0 blocked、0 false completion；正常层为2/12。T7 整体为 **`DONE`**，最终454项回归及独立runtime审查已通过；该开发结果不是正式 G1。

## 三个执行范围

| `execution_scope` | 执行内容 | 模型调用 | 任务执行结果 |
| --- | --- | --- | --- |
| `CAPTURE_ONLY` | 保存真实仿真相机的 RGB、深度与观测元数据 | 无 | `task_execution=NOT_RUN`、`task_success=false` |
| `VISUAL_PLANNING` | 采集 RGB-D，调用视觉模型并验证规划合同 | 有 | `task_execution=NOT_RUN`、`task_success=false` |
| `VISION_CLOSED_LOOP` | 采集、规划、技能执行、动作后重采集、条件验证和末尾独立评分 | 有 | 根据实际在线验证和物理评分判定 |

`LEGACY_PIPELINE` 是显式选择的旧链路。默认 RGB-D 请求不会静默回退到 Mock 或旧链路；模型、相机、冻结证据或执行环境不可用时应保留阻塞或失败结果。

闭环复用同一个 MuJoCo backend 和 episode。动作后重采集产生新的 `frame_id`，不会通过 reset 恢复初始状态。借用已初始化 backend 的 `MuJoCoCaptureSession` 不负责初始化、reset 或 shutdown；资源由原 owner 释放。

## 冻结模型与独立运行目录

从仓库根目录执行下列命令。先准备可用的 MuJoCo/EGL 环境及已验真的冻结模型目录；模型服务需与冻结记录一致。冻结目录包含 `model-frozen.json`、`model-frozen-evidence.json`、`probe-report.json`，加载时会检查证据完整性与漂移。

工作台的 HTTP 和 WebSocket 入口都使用 `ModelControlService.visual_planner` 工厂。解析优先级是当前 active profile，其次才是在没有 active profile 时读取 `BIGSMALL_VLM_FROZEN_DIR`；未设置冻结目录时使用普通环境配置。**设置冻结环境变量不会覆盖 active profile。**

研究运行使用一个新目录中的 `MODEL_CONTROL_DB`，使该实例从空 profile 开始。不要清空或修改用户正在使用的模型数据库：

```bash
mkdir -p artifacts
T7_RUNTIME_DIR="$(mktemp -d "$PWD/artifacts/t7-runtime-XXXXXX")"
export MODEL_CONTROL_DB="$T7_RUNTIME_DIR/model_control.db"
export DASHBOARD_ARTIFACT_ROOT="$T7_RUNTIME_DIR/artifacts"
export BIGSMALL_VLM_FROZEN_DIR="$PWD/artifacts/research/process/20261003-t7-visual-closed-loop/model-probe"
export MUJOCO_GL=egl

.venv/bin/python -m uvicorn cloud_edge_robot_arm.cloud.api.app:create_app \
  --factory --host 127.0.0.1 --port 8000
```

该服务进程使用上述独立数据库和 artifact 根目录。已有服务仍保留其原配置；向 API 发请求时应使用本次启动的端口。若之后在这个新数据库中启用了 profile，后续请求将优先使用该 profile。

## 同 episode 闭环开发 smoke

下面是本轮已执行的 `smoke-20-v2` 命令。CLI 直接通过 `--frozen-dir` 加载冻结模型，不读取工作台 active profile。该目录已存在，重跑时必须换用新目录，不能覆盖或续写本轮证据。

```bash
MUJOCO_GL=egl .venv/bin/python scripts/run_rgbd_smoke.py \
  --scope closed-loop \
  --episodes 20 \
  --config configs/research/visual_smoke.yaml \
  --frozen-dir artifacts/research/process/20261003-t7-visual-closed-loop/model-probe \
  --output artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2
```

输出目录必须不存在；重复运行应分配新的目录并保留旧证据。脚本预先写入全部20个独立场景的分配：正常场景、目标缺失、无效深度和预置安全停止。v2与v1使用同一批20 assignments，全部失败与成功都保留。该配置是开发smoke，不是正式G1评估协议。

主要证据包括：

- `assignments.json`、`config.yaml`、`provenance.json`：预分配场景、配置、冻结包和相关源码指纹。
- `cases/<case_id>/`：本次场景、观测、验证记录、`physical-evidence.json`、`physical-outcome.json`、`episode.json` 和 `case-result.json`。
- `progress.json`、`results.json`、`summary.json`：运行进度、全部已分配样本的结果与 smoke gate 判定。

退出码 `0` 表示脚本的开发 smoke gate 通过，`1` 表示未通过，启动参数或目录等错误可返回 `2`。判断时应同时查看全部样本、阻塞原因、失败原因和物理证据，不把返回了规划 JSON 或某个技能调用成功当作任务成功。

## 独立数据生成作业

数据生成使用 `job_type=DATASET_GENERATION`，复用现有 RGB-D dataset generator，不调用视觉模型。它必须同时满足：

- `backend=MUJOCO`、`input_mode=RGBD`、`execution_scope=CAPTURE_ONLY`。
- 提供 `dataset_config`；普通 `SIMULATION` 作业禁止携带该字段。
- `run_type=SINGLE`，单个 scenario、control mode 和 seed，`repetitions=1`；组数通过 `dataset_config.groups` 配置。
- 使用已注册资产 `assets/robots/franka_panda/scene.xml`；输出目录由 worker 固定为该 job artifact 目录下的 `dataset/`，草稿不能指定外部输出路径。

以下示例生成一组数据。请求头适用于默认 `LOCAL_ONLY` 鉴权下的可信本机请求；使用 TOKEN 模式时，应改为具有 `EXPERIMENT_OPERATOR` 权限的认证方式。

```bash
curl --fail-with-body http://127.0.0.1:8000/api/v1/simulation/runs \
  -H 'Content-Type: application/json' \
  -H 'x-dashboard-role: EXPERIMENT_OPERATOR' \
  --data-binary @- <<'JSON'
{
  "backend": "MUJOCO",
  "job_type": "DATASET_GENERATION",
  "run_type": "SINGLE",
  "input_mode": "RGBD",
  "execution_scope": "CAPTURE_ONLY",
  "scenarios": ["S01_NORMAL_STATIC"],
  "control_modes": ["PCSC"],
  "seeds": [72001],
  "repetitions": 1,
  "dataset_config": {
    "dataset_id": "rgbd-workbench-example",
    "groups": 1,
    "seed": 72001,
    "width": 320,
    "height": 240
  }
}
JSON
```

`POST /api/v1/simulation/runs` 返回 `202` 和排队后的 run。使用返回的 `run_id` 查询 `GET /api/v1/simulation/runs/{run_id}`，并通过该 run 的 artifacts 查看 `result.json` 与 `dataset/manifest.json`。`dataset_config.seed` 决定 dataset 内部采样，示例将它与作业 seed 对齐。

数据 manifest 的 `COMPLETE` 对应作业 `SUCCEEDED`，表示数据生产完成；结果仍为 `task_success=false`、`task_execution=NOT_RUN`、`model_calls=0`。生成未完成或失败不会统一映射成成功；环境阻塞会保留 `BLOCKED_BY_ENV`。

取消和超时会停止继续生成，并保留已提交的样本及 manifest。调度层分别记录 `CANCELLED` 或 `TIMED_OUT`；超时触发 generator 的取消回调时，dataset manifest 可以记录 `CANCELLED`，同时 job 记录 `TIMED_OUT`，分别描述数据生成停止状态和调度终止原因。

## 如何解释闭环结果

| 字段 | 含义 |
| --- | --- |
| `online_reported_complete` | 在线证据验证链是否报告完成；不等同于独立物理成功 |
| `physical_success` | episode 末尾独立物理评估器的结论 |
| `terminal_reason` | 取消、超时、安全拒绝、证据不足、预算耗尽或环境阻塞等终止原因 |
| `semantic_success` | 运行结束后的独立语义判定；工作台 S01 使用固定任务参照，smoke 使用预分配任务，例如目标缺失样本不能算成功 |
| `task_success` | 要求在线完成、物理成功、没有终止原因，且独立语义判定通过 |

语义评分属于闭环尾部评分，采集或规划作业不据此声明任务成功。`visual_episode_success` 保留引擎的在线与物理合取结果，便于与加入独立语义要求后的最终结果区分。`false_completion` 表示在线报告完成但最终任务判定失败。

工作台 S01 的 `s01-task-semantics-v1` 仅对固定资产的红块到绿区任务判定语义通过，完整句子限定为 `将红色方块放到绿色区域` 或 `Move the red block to the green region.`，只忽略首尾空白。同一规范句式的其他目标颜色返回 `FAIL`；否定、多目标、不同目的地和未列出的改写返回 `UNKNOWN`。二者都会使最终 `task_success=false`，不会通过包含“红色”或 `red` 的子串来判定成功。

该判定发生在执行结束后，不是在线指令理解门禁。模型仍可能误选对象并在语义失败被判定前执行动作；尾评分会保留这种错误动作与 `false_completion` 证据，不能据此声称已预防所有误抓。任意自然语言指令和多目标任务仍在当前支持范围之外。

在线执行使用 RGB-D、机器人状态和统一条件验证结果。物理真值只在末尾独立评分，预分配语义标签也不参与在线动作选择或恢复。颜色追踪从模型选中的像素及后续 RGB-D 提取观测，不能把仿真目标位置、实例 ID 或评分布尔值当作在线感知证据。

## 当前边界与运行防护

当前闭环支持 MuJoCo `S01_NORMAL_STATIC` 和已校准的当前机械臂资产，抓取假设为水平支撑面上的直立刚性方块（upright box），使用可区分颜色跟踪目标。抓取几何采用 `mujoco_upright_box_v1` 标定；资产漂移、颜色歧义、遮挡或深度无效不能据此推广成通用物体抓取能力。

可选 `HOME` 不参与当前闭环执行。运行合同编译记录保留被省略的步骤，并记录 `NOT_EXECUTED_OPTIONAL_HOME_FIXED_SPEED_NOT_VERIFIABLE`；不能将其计入已执行动作。

执行经过既有 `SkillExecutor` 和 `SafetyShield`，逐步验证前置条件、动作后条件及安全约束。运行记录包含实际合同、运动参数和研究策略的安全范围；研究策略不改变全局默认门槛。低位 `LIFT` / `RETREAT` 只允许具有完整目标姿态、XY 不变且上升至安全高度的脱离动作。关节速度检查使用绝对值。

默认验证预算来自 [visual_smoke.yaml](../configs/research/visual_smoke.yaml)：

| 预算 | 默认值 |
| --- | --- |
| 重新观测次数 `max_reobservations` | 2 |
| 重试次数 `max_retries` | 0 |
| 无进展次数 `max_no_progress` | 3 |
| 验证截止时间 `deadline_s` | 120 秒 |

episode 默认超时同为 120 秒。`UNKNOWN` 不能作为继续动作的通过条件，只能按剩余预算请求新观测或停止；预算已耗尽时，即使单个条件为 `PASS`，路由也可以返回 `STOP`。取消、超时及租约失效会阻止后续执行，物理步进检查取消状态；超时或取消后迟到的模型回复不再触发动作。

## 证据状态

截至本文编写时，已有一组真实 MuJoCo 数据作业记录为 `COMPLETE` / `SUCCEEDED`，`model_calls=0`、`task_success=false`，见 [data-job-real/result.json](../artifacts/research/process/20261003-t7-visual-closed-loop/data-job-real/terminal-test/result.json)。它验证独立数据生产路径，不代表视觉闭环完成验收。

`smoke-20-v2` 已保留20/20分配：2正常成功、18失败、0 blocked、0 false completion，正常层2/12，全分配2/20（10%）。[独立复算](../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)核对34,353个物理样本、154帧和52动作，返回 `valid=true, accepted=true, errors=[]`。v1的全20失败及34份源码快照、22,147样本、105帧、33动作原样保留；diagnostic-03成功另列。结果限当前MuJoCo直立有色方块的开发smoke，`formal_g1=false`，不能外推正式任务成功率。

95项runtime和277项prerequisite测试是阶段记录，最终454项回归通过，T7仍为DONE。最终验收见根任务在[T7过程证据目录](../artifacts/research/process/20261003-t7-visual-closed-loop/)发布的 `acceptance.md`。共享capture变更后的现行模型已经在T7目录重探4/4并冻结；历史T3/T5来源按原时点保存，不能把旧source freeze当作现行绑定。T6b的10000组和真实硬件未运行，未commit/push。

相关入口：[Simulation Workbench](simulation_workbench.md)、[MuJoCo Backend](phase9_mujoco_backend.md)、[T7 研究路线图](superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
