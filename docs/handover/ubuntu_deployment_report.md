# BIG-small Ubuntu 部署与验收交接报告

记录日期：2026-10-02。项目当前全部按 **Sim2Real 模拟设备路线**开展：MuJoCo 主批量设备、Isaac 对照设备、ROS2 / MoveIt 模拟控制器与规划。真实设备阶段禁用，S3/S4 保持 LOCKED。既有 Cloud → TaskContract → Edge Validator → Safety Shield → Skill Executor → RobotAdapter 架构、PCSC / ETEAC / AUTO 与版本/序号/TTL/ACK 防护保留。

本次形成了可启动、可开发、可测试的 Ubuntu 仿真研究环境；严格跨引擎物理配对、完整 Isaac 参数应用、真实模型性能和 full 最终封板尚未接受。本文记录部署验收，不是开题报告。论文工作仅复现已有管线，未重新设计研究项目。

## A. Git

集成分支：`codex/ubuntu-integrated-deploy`。基线 / upstream：`origin/codex/macos-local-dev`，`3c2b5fd18f885367f543eae23c0e3d18343a84df`。交付后的精确 SHA、ahead/behind 和 clean 状态以 [final_acceptance.json](../../artifacts/deployment/final_acceptance.json) 及 `git rev-parse HEAD` 为准，避免将报告本身的提交 SHA 循环写入源文件。

首次 fetch 与交付前 fetch 均已执行。远端 SHA 和拓扑未变化：

| 分支 | 首次核验的 SHA |
| --- | --- |
| main | 5c43450eab1dd29b5a32786fb506f503b2729d4e |
| codex/thesis-report | aac89d077f46f3a90e1da5aafa8b9c95db35f00d |
| codex/sim2real-workbench | d741c37de1adba5fb23b78ae3bf18aa4f38a4154 |
| codex/macos-local-dev | 3c2b5fd18f885367f543eae23c0e3d18343a84df |
| codex/phase13-real-llm-baseline | c2fd244fdc1784cf2340c30c07d12e9f37e79049 |

thesis → sim2real ahead 2 / behind 0 → macOS ahead 2 / behind 0。Phase13 相对 thesis ahead 4 / behind 31，merge-base 为 `13ac69834de901443c6b0782842216d562ff88a6`；已审阅 unique commit diff 和 range-diff，逐项 cherry-pick 四个提交，没有整体覆盖新主线、论文、CI 或 macOS 支持。没有 push、force push 或合并 main。

正式证据的代码版本分别保留，不能改写为最终交付 SHA：

- `d571e1b03a4201c51d36c0d2cbaabd91fce734c9`：全 Python 门禁、Phase12 full、最终 ROS/MoveIt/Isaac 运行、launcher。
- `b35e53905c4f50a3c94435bff12bbec1c5a9030c`：工作台完整门禁与 37 E2E，之后 fast-forward 纳入主工作区。
- `da299bd9bd423e5c576b9492d30ccabba876cc05`：配对 repetition 聚合修复和独立重分析。

原 macOS 基线已有 tracked artifacts 没有修改或删除；Phase13 原分支新增 artifacts 随审阅的提交迁移。初始审计见 [git_baseline.json](../../artifacts/deployment/git_baseline.json)，交付溯源见 [git_delivery_provenance.json](../../artifacts/deployment/git_delivery_provenance.json)。

## B. Environment

| 项目 | 主机实际结果 |
| --- | --- |
| Ubuntu / kernel | 24.04.5 LTS / 7.0.0-38-generic |
| CPU / RAM | Ryzen 7 5800X，8 cores / 16 threads；67,326,935,040 bytes，约 62.7 GiB |
| GPU / driver | RTX 4070 Ti SUPER，16376 MiB；NVIDIA 595.91.07 |
| CUDA | 驱动显示支持 13.2；PyTorch 2.11.0+cu130 实际 runtime 13.0，GPU tensor 运算结果 14.0 |
| 图形 | Vulkan 可见 NVIDIA；X11 DISPLAY=:1；实际 headless Isaac 已运行 |
| 核心 Python / pip | 独立 .venv，Python 3.12.3 / pip 26.2.1；pip check PASS |
| Node / npm | 22.23.3 / 10.9.9，官方 SHA256 校验后安装；npm ci 使用原锁文件 |
| MuJoCo / Rerun | 3.3.7 / 0.38.1 |
| ROS2 / MoveIt | RoboStack Jazzy 独立 micromamba 环境；MoveIt 2.12.4，desktop 0.11.0，Panda config 3.1.0 |
| ROS workspace | `$HOME/bigsmall_runtime/ubuntu-6bebc95b/ros2_ws`；ASCII 路径，六个 packages 构建通过 |
| Isaac Sim | 独立 `cache/isaac-sim-6.0`，6.0.0.1；项目简化 Franka-like MJCF 转 USD；用户已明确接受 EULA |
| Isaac Lab | 官方 tag 3.0.0-beta2，commit 28a37cecdd433c22d9eabd6a5954add9f13a8951；extension version 6.1.11，独立 env |
| Ollama / compatible model | 无可用 daemon/已有模型；无用户提供的 compatible endpoint/key |
| Docker | 未安装；已使用 standalone Isaac / 用户态 ROS，无需 Docker 完成本次运行 |

核心 extras 按 pyproject 和 Linux constraints 安装：dev、sim-mujoco、sim-analysis、sim-observability。ROS、Isaac 和 Lab 分环境保存。Lab coverage 7.6.1 与 isaacsim-kernel 要求 7.4.4 存在上游依赖冲突，记录为 WARN，没有改动核心环境掩盖冲突。初始 sandbox GPU 不可见观察已保留，当前 GPU/CUDA 结论来自实际主机探针与 GPU 运算。

完整命令输出见 [system_inventory.json](../../artifacts/deployment/system_inventory.json)、[system_inventory.md](../../artifacts/deployment/system_inventory.md)、[dependency_report.json](../../artifacts/deployment/dependency_report.json)。

磁盘：`df -h .` 显示 1.2T SSD，约 70G 已用、1012G 可用、7%。`du -sh`：核心 venv 1012M；Isaac 25G；Lab env 1.3G / source 118M；ROS/mamba 8.8G；核心 pip cache 367M、Isaac pip 995M、Lab pip 304M、npm 75M；Chromium 646M；Node 203M；node_modules 456M；artifacts 128M；results 3.4G。精确时点输出见 [disk_usage.json](../../artifacts/deployment/disk_usage.json)。

默认保留结构化 telemetry、JSON/JSONL/CSV、metrics、manifest/hash/provenance。RGB/depth/video 只保存代表、异常、论文 figure 或明确请求的 case；本次没有下载任意模型，也没有自动删除历史成果。

## C. Validation

| 子系统 | 状态 | 已验证范围与限制 |
| --- | --- | --- |
| Core | PASS | Ruff、mypy、全量 769 pytest、pip check；后续配对统计修复另有 18 项定向回归 |
| Dashboard | PASS | api drift / format / lint / type / 24 unit / build / 37 E2E，无 skip；实际 MuJoCo worker 断言 |
| MuJoCo | PASS | 模型/MjModel/MjData/step、adapter、worker、四级 DR、确定性采样和 MjSpec 物理应用 |
| ROS2 | PASS | 实际消息/service/action、cancel/timeout、crash/reconnect、namespace、持久 workspace |
| MoveIt | PASS | 实际 planning/collision/SafetyShield、模拟控制器；MOVEIT_RUNTIME dry-run，不连接真实控制器 |
| Isaac | WARN | 实际 app/模型/TCP/关节/RGB/depth/contact/step/reset/estop 通过；完整物理 DR 与 Lab EventManager 应用未接受 |
| Sim2Real | WARN | calibration/envelope/coverage/matrix/export/batch/locked API/UI 和离线 viewer 通过；严格物理配对和 gap 未接受 |
| Phase13 | BLOCKED | fake B01/B02/B03 管线完成；真实模型 baseline 未运行，无性能 accepted evidence |
| Phase12 | WARN | smoke 闭环通过，full 和修正重分析完成；full verifier exit 1 / PHASE12_REJECTED，不能封板 |
| Thesis | WARN | 历史 evidence/build 可复现，DOCX/PDF 全页渲染检查；新 full 素材独立导出，最终结论与提交版未接受 |

状态索引在 [final_acceptance.json](../../artifacts/deployment/final_acceptance.json)，每个组件有 deployment JSON 与原始证据链接。Doctor 只检查依赖可用性，退出 0 仍可能包含 WARN/BLOCKED，不能代替 runtime 验收。

## D. 实际执行与结果

| 实际命令或流程 | 真实结果 / 证据 |
| --- | --- |
| `python -m ruff format --check .` / `python -m ruff check .` | PASS |
| `python -m mypy .` | d571 门禁 PASS；统计修复后 PASS，520 source files |
| `python -m pytest -q` | d571：769 passed，1 Starlette/AnyIO deprecation warning，10248.41s |
| 配对修复相关 pytest | 两个回归在旧代码失败；修复后 13 + 5 = 18 passed，代码只改变配对分组 |
| `python -m pip check` | 核心环境 PASS；Lab 冲突单独记录 |
| Dashboard `npm ci` / `api:check` / `format:check` / `lint` / `typecheck` / `test` / `build` / `e2e` | 全部 PASS；24 unit，37 E2E；仅 Vite chunk 大小警告 |
| Phase0/1 examples、固定 mock task，Phase2/3/3.1/3.2/4/5/6/6.2/7/8/8.1/8.2，Phase9 MuJoCo/randomization/physics/safety verifiers | 全部命令 exit 0；软件/Mock/MuJoCo 范围，见 phase_validation.json |
| Phase9.1 最终 ROS2 / MoveIt / Isaac verifier | 三组件 VALIDATED、安全压力通过；aggregate PHASE9_1_REJECTED，旧 schema 跨后端 artifact 未接入。未伪造兼容 artifact 强行通过 |
| Phase10_0/10_1/10_2a + actual MoveIt evidence | PHASE10_MOVEIT_DRY_RUN_ACCEPTED；早期跨 SHA 拒绝记录保留 |
| Phase10_2b backend / Level0 fake | 软件框架通过；不是实际机器人只读或运动验收 |
| Phase11_1 full / Phase11_2 CI | b35：SIMULATION_RUNTIME_ACCEPTED / SIMULATION_AI_CONSOLE_ACCEPTED；真实本地模型仍未接受 |
| MuJoCo DR probe | NONE/MILD/MODERATE/SEVERE × seeds 0/1/17，12 个实际 compiled-model samples 与 step；相同 seed 重复可复现 |
| Isaac standalone / Lab probe | 实际 GPU app 与 adapter smoke 通过；Lab 在 app 中物化 5 event terms + actuator/noise config，validation_claimed=false |
| 原 Phase9.2 30-pair 管线 | 两后端实际调用、旧 verifier 通过；初始状态/目标/控制/时长不匹配，不能当公平物理对比 |
| Rerun `rrd verify` | 实际两后端轨迹、sensor fields、原生时间轴离线 recording：1 file verified without error；未伪造时间戳事件 |
| Sim2Real gap API 边界 probe | SIM/ISAAC_SIM 输入返回 HTTP 422，要求 REAL comparison trace；边界通过，物理 gap NOT_ACCEPTED |
| Phase13 checker / fake run / analyze / figures / verify / thesis update | 9 fake rows、fake authoritative 0、accepted 0、source hash verified、contains_secret=false |
| Phase12 smoke run / analyze / export / verify | 90 SYNTHETIC_PIPELINE_SAMPLE，actual runtime 0，管线 READY |
| Phase12 full run / analyze / export / verify | 前三步 exit 0；verify exit 1。5,580 行，5,040 runtime-completed、540 运行前阻塞 |
| full 独立重分析 / export / verify | 前两步 exit 0，verify 仍 exit 1；输入 77,225 文件哈希核验、原始数据不变 |
| thesis evidence / tables / figures / references / build / figure/claim/build checks | 历史复现 PASS；35 references、28 formal figures，DOCX 14 rendered pages、PDF 39 pages |
| `scripts/linux/start.sh` 实际启动 probe | API、Dashboard、frontend proxy 均 HTTP 200；创建 202，内置 Mock worker SUCCEEDED；只回收本次进程组 |

全 Python 门禁源代码为 d571；b35 仅修改前端 E2E，da299 仅修改配对聚合及其测试。没有将旧全量测试的 SHA 改写为新提交，也没有宣称 da299 重新跑过整个 769-suite。当前源码范围由旧全量门禁和新变更的定向回归共同覆盖。

Phase12 新 full 的状态计数为 SUCCESS 3960 / FAILED 480 / SAFETY_STOPPED 600 / BLOCKED_BY_ENV 540。runtime backend 标签为 MOCK 3330 / MUJOCO 990 / ISAAC_SIM 180 / SYNTHETIC_DRY_RUN 360 / PLANNER_DRY_RUN 180；runtime-completed 不是任务成功，也不是全部为物理设备运行。失败、安全停止和阻塞样本全部保留。

原聚合忽略 repetition，180 次配对被压成 60 对；修复后原始 360 个 F15 backend rows 形成 180 对，其中 120 对满足旧标量统计规则、60 对含安全停止。旧 summary 原样保留，修正输出位于 `results/20261002-da299bd9/phase12-full-reanalysis`，producer SHA 仍为 d571，analysis SHA 单独记录。full 仍拒绝，verifier-gated authoritative thesis run count 为 0。

修复还覆盖：Phase13 非空模型文本被误判有效/任务成功；Isaac JSONL stdout 已有 ACK 却因缓冲超时；Linux 公共 env 全局 DB 导出导致实验共库；E2E 共用 fixture、删除活跃 DB、batch 未排空、API cwd 导致 MuJoCo 资源丢失和已配置 Isaac 与 blocked 用例冲突。E2E 现在每次使用独立绝对路径；MuJoCo 用例必须 SUCCEEDED、runtime_executed=true、mock_fallback=false、physics_steps>0，并等待结果文件实际写完。未删除测试、未增加 xfail、未放宽安全标准。

部署自建的旧 DEV 数据库在确认没有进程持有后，逐字节归档到 `results/deployment-legacy-dev-db-20261002`，附 hash manifest；默认开发 DB 已重新初始化。各正式实验 DB 和 artifacts 保留。测试隔离 worktree 的三个正式 E2E 目录已按 hash 复制保存。

## E. Remaining blockers

1. **Isaac 完整参数应用 / 严格配对未接受。** 当前 stock trial 两端初始关节、目标、控制方式、时间步和时长不同，Isaac 直接设置关节位置。DR shared values 配置一致，但完整 friction/damping/gains/gravity/delay/noise 的实际 scene 应用与 Lab EventManager 尚未验收。要求的公平 TCP/joint RMSE、sensor latency RMSE、timestamp skew p95、task outcome、collision/safety、duration 差距没有有效严格配对报告。
2. **Gap Report 模型边界。** 既有 API 是 Sim/Real offline comparison，需要真实采集 trace；当前全模拟设备路线没有 REAL trace，不能改标签绕过。跨引擎比较需要后续在既有工具链中补齐明确的 simulator-pair 语义与匹配 trial，不得暗示硬件验收。
3. **Phase12 MoveIt 接线未完成。** 360 条固定 BLOCKED 来自 `Phase10MoveItDryRunAdapter`，并非本机 MoveIt 未安装。独立 MoveIt 已通过，Phase12 adapter 尚未调用它。原 verifier 顶层固定 ISAAC_SIM / OLLAMA_RUNTIME 环境标签不准确，应以逐行 execution_source 与源 artifact 为准。
4. **真实模型服务未配置。** 180 条 full planner 阻塞来自 compatible planner；Phase13 Ollama/compatible 均 BLOCKED。fake 与模型响应仅用于管线检查，不能认作实际任务执行成功或安全执行验收。
5. **最终论文证据与版式。** 历史 466/74 论文已复现；新 full 的 statistics/tables/figures/thesis assets 独立生成，但 full 拒绝。现有 manuscript 仍含历史数字与 old full-not-run 语句；作者信息留空、PDF/DOCX 摘要不一致、章节标签重复。当前产物是历史构建复现，不是已更新到新 full 的最终提交版。
6. **Lab 上游 coverage 冲突。** 环境隔离保留，配置物化通过；不能据此声称训练/物理随机化全部通过。

这些限制没有通过修改历史 artifact、降级安全规则或将 simulation/fake/synthetic 重标为 REAL 消除。现有部署足以继续模拟设备研发；研究最终封板仍需上述证据。

## F. Safety boundary

```text
real_robot_validation=NOT_STARTED
real_controller_contacted=false
hardware_motion_observed=false
hardware_write_operations=[]
highest_real_hardware_acceptance_level=NONE
real_motion_dispatch_enabled=false
S3=LOCKED
S4=LOCKED
```

没有 servo enable、brake release、真实 trajectory dispatch、MoveIt execute 到真实控制器或真实设备读写。云端、浏览器和模型无法绕过边缘契约验证与 Safety Shield。密码/模型 key 未写入代码、报告或实验 artifact；EULA consent 仅在 ignored 本机配置中保存。

## G. Commands

从项目根目录执行。安装脚本用于核心 extras、locked npm 与 Chromium；外部 Node、NVIDIA、ROS/MoveIt、Isaac、Lab 和 TeX 已独立部署，不由核心 pip 混装。

```bash
./scripts/linux/install.sh
./scripts/linux/doctor.sh
./scripts/linux/start.sh
# 另一个终端可以运行 smoke；full 前先 Ctrl-C 停止开发服务
./scripts/linux/test.sh --smoke
./scripts/linux/test.sh
```

启动后的 Workbench：<http://127.0.0.1:5173/simulation/workbench>；API：<http://127.0.0.1:8000/docs>。在启动终端 Ctrl-C 停止服务。E2E 使用 8000/5173，full 测试前先停止占用这些端口的开发服务，多个验收程序请串行运行。

每次实验创建新目录；正式实验前保持 Git clean。以下是现有运行入口，跨后端命令只运行旧配对管线，不自动解决 E 节的公平物理配对限制。

```bash
source scripts/linux/env.sh
test -z "$(git status --porcelain)"
export TASK_RUN_ROOT="$PWD/results/$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short HEAD)-$$"
mkdir -p "$TASK_RUN_ROOT"
export SIM_ARTIFACT_DIR="$TASK_RUN_ROOT/runtime"
export ISAAC_SIM_BACKEND_CMD="'${ISAAC_SIM_ROOT}/bin/python' '${BIGSMALL_ROOT}/scripts/phase9/isaac_standalone_app.py' --output '${TASK_RUN_ROOT}/isaac-process'"

# MuJoCo 实际批量仿真；默认不录视频
python scripts/run_phase9_benchmarks.py --backend mujoco --suite smoke \
  --headless --output "$TASK_RUN_ROOT/mujoco"
# Isaac actual app/adapter smoke
python scripts/verify_phase9_2_isaac_smoke.py --output "$TASK_RUN_ROOT/isaac"
# Sim2Real 现有跨引擎运行管线（其 PASS 不等于公平物理 gap）
python scripts/run_phase9_2_cross_backend.py --run-experiments \
  --output "$TASK_RUN_ROOT/cross-backend"
# Phase13 fake smoke，不能用于真实模型性能结论
python scripts/check_llm_provider_environment.py --provider fake \
  --output "$TASK_RUN_ROOT/phase13/environment"
python scripts/run_phase13_1_experiments.py --provider fake --profile smoke \
  --output "$TASK_RUN_ROOT/phase13"
python scripts/analyze_phase13_1.py --root "$TASK_RUN_ROOT/phase13"
python scripts/build_phase13_1_figures.py --root "$TASK_RUN_ROOT/phase13"
python scripts/verify_phase13_1.py --root "$TASK_RUN_ROOT/phase13"
# 有真实服务时先检查；当前本机仍 BLOCKED，不自动下载或付费调用
python scripts/check_llm_provider_environment.py --provider ollama \
  --output "$TASK_RUN_ROOT/model-environment"
python scripts/check_llm_provider_environment.py --provider openai-compatible \
  --output "$TASK_RUN_ROOT/model-environment"

# Phase12 smoke；full 可将 profile 与最后的 --smoke 改为 full / --full
python scripts/run_phase12_experiments.py --profile smoke --output "$TASK_RUN_ROOT/phase12"
python scripts/analyze_phase12_results.py --profile smoke --output "$TASK_RUN_ROOT/phase12"
python scripts/export_phase12_thesis_assets.py --profile smoke --output "$TASK_RUN_ROOT/phase12"
python scripts/verify_phase12.py --smoke --artifact-root "$TASK_RUN_ROOT/phase12" \
  --output "$TASK_RUN_ROOT/phase12/verification"
# 离线查看实际 native traces
rerun results/20261002-d571e1b0/trace-viewer/native-sensors/native-traces.rrd
```

已有论文 build 会写 `docs/thesis` / `thesis`，复现时使用隔离 clone，以免改写主工作区历史生成物。以下使用既有历史 evidence，不能称为新 full 最终结论：

```bash
export TASK_REPO_ROOT="$PWD"
git clone --local --no-hardlinks "$TASK_REPO_ROOT" "$TASK_RUN_ROOT/thesis-reproduction"
(
  cd "$TASK_RUN_ROOT/thesis-reproduction"
  python scripts/build_thesis_evidence.py
  python scripts/build_thesis_tables.py
  python scripts/build_thesis_figures.py
  python scripts/verify_thesis_references.py
  python scripts/build_thesis.py --output "$TASK_RUN_ROOT/thesis-output"
  python scripts/check_thesis_figures.py
  python scripts/check_thesis_claims.py
)
```

本次已生成的历史论文位于 `results/20261001T193000Z-6bebc95b/thesis-historical-reproduction/outputs-retry1/`；新 full 与修正 statistics 分别位于 `results/20261002-d571e1b0/phase12-full/` 和 `results/20261002-da299bd9/phase12-full-reanalysis/`。报告 JSON 的早期版本逐字节保存在 `artifacts/deployment/report-revisions/20261002-before-final/`。
