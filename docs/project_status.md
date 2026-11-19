# 项目状态

## 2026-11-19 项目组状态

BIGsmall Embodied Harness 已交付 H0/H1 工程开发版，冻结首场景契约并通过清洁环境安装、七条 CLI 正常路径和两条保护拒绝检查。历史四位姿冻结于 `5103e7f4`，本轮新增开发位姿冻结于已含 worker 异常留痕的 `4bdb64eb`。教师单组入口与采集优化另在研发分支 `research/harness-candidate-20261118` 交付。云端负责规划，边缘按规则和成本约束判断，端侧用 OpenCV/RGB-D 观测，沿用可见姿态标记、顶视相机、现有控制器与安全盾。边缘模型选型后置。 [现行计划](plan.md) · [公开交付范围](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-candidate-generalization-20261118/implementation/public-delivery.md)

冻结版首次整库收集 7,259 项，7,225 通过、33 跳过、1 项 dispatcher 清理错误，原判定为 `passed=false`。同版在原测试夹具下独占复验该节点通过，退出 0。 [回归、安装与固定场景回放](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-candidate-generalization-20261118/implementation/regression-and-install.md)

### 四个同版本 MuJoCo 开发位姿

四例各运行一次，组件完整执行 **1/4**，独立物理成功 **1/4**，物理记录中检出安全违规 **0/4**。本批实际有 3 次付费云请求（GPT-6.1-Sol）、14 次本地生成（Molmo2-ER）、4 次加载、0 次重试，账单金额未知（`null`）。 [四例报告](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-four-fresh-positions-20261118/final-batch-report.md) · [逐槽机器回执](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-four-fresh-positions-20261118/final-batch-summary.json)

| 位姿 | 结果与原因 |
| --- | --- |
| `2026111801` | 放置阶段第 5400 步，采样与逆运动学耗时 100.041 ms，超过原 100 ms 门，触发保护停止，未形成稳定放置。 |
| `2026111802` | 全部动作执行完成，两段退避结束，终帧观测到已登记标记。独立物理复算确认稳定放置 9.475 秒。 |
| `2026111803` | MOVE_ABOVE 初始化停止，尝试 1 次、执行 0 次。在线 worker 只记录 `ValueError`。冻结帧和同版构造器离线复算显示，规划抓取点与标记配准估计相差 30.882 mm，超过原 10 mm 身份门。 [初始化前缀复核](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-fresh-1803-initialization-prefix-20261118/step-report.md) |
| `2026111804` | 压力位姿的两个本地点位均返回。现有归档复算的目标顶面高度跨度为 8.027 mm，超过原 8.000 mm 门。初始规划请求更多观测，云请求和动作均为 0。 |

历史开发位姿四例仍为组件完成 1/4、独立物理成功 2/4。含这四例的跨版本历史七例分别为 3/7 和 4/7。 [历史七例独立复算](../artifacts/research/process/20261004-ced-development/astra-rounds/round-harness-candidate-generalization-20261118/implementation/native-seven-verification.md)

### 三例归档复核与 worker 修复

三例全部从 `5103e7f4` 的冻结 RGB-D、标记和执行原件重建，零新增模型调用。九份确定性结果经独立复算逐字节一致。 [输入与完整读回](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-archived-three-20261119/step-report-v2.md)

| 位姿 | 找到的首个差异及处置 |
| --- | --- |
| 1803 | 原指点 (173,120) 通过 3×3 颜色检查，距登记顶心 6.237 像素。反投影后已出现 30.848 mm 的 TCP 横向差，全三维差 30.882 mm。1802 的关联将偏差从 8.836 像素降到 0.329 像素，最终 3.059 mm。两条路径均复现相同的刚体配准，物理成因为 `UNKNOWN`。 [登记叠图](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-archived-three-20261119/derived-v2/1803-1802-registered-identity.png) |
| 1801 | 两例各有 143 个单主视图接受样本。1801 两次启用备选视图时，视觉处理 47.664 ms、捕获归档 29.716 ms、移机 10.153 ms，最终 100.041 ms 触发保护。最近系统采样在 4.155 秒后，1/5/15 分钟负载为 1.26/1.97/4.08。身份、时间、顺序和安全检查需同步完成。大文件异步写入仍需证明哈希登记可恢复、有界回压与落盘完整性。 [视图与分项耗时](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-archived-three-20261119/derived-v2/1801-place-timing.json) |
| 1804 | 205 个支持像素中，147 个核心像素跨度 4.845 mm，203 个顶面像素跨度 8.0266 mm，原门限为 8.000 mm。两个极值都在有 RGB-D 过渡的边界。表面起伏、混合像素或遮挡的物理归因仍为 `UNKNOWN`。 [极值与 5×5 深度邻域](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-archived-three-20261119/1804-extrema-neighborhood-depth.png) |

worker 自产品提交 `4bdb64eb` 起，把脱敏后的异常类型、消息、堆栈和阶段写入 episode。原停止条件沿用。定向回归 34/35，余下一项成功路径在同源独占复验通过，原 113.520 ms 超限记录保留。 [异常原件与回归](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-worker-exception-20261119/step-report.md) · [同源独占结果](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-worker-types-exclusive-deadline-20261119/step-report.md)

### 教师、B0 和交付环境

教师已从九个新组中单独开放 `native-p0-20261119-0001`。优化成功采集的不可变数据快照后，同一姿态在原 8 秒窗口内的实测进度由 181/1920 提至 391/1920 步。16 帧均有当前注册区域，红色身份仍出现分裂。正式验收要求独立 reader 重建八个完整动作。 [单组协议](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-first-teacher-20261119/step-report.md) · [原窗复验](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-capture-detach-20261119/step-report.md)

B0 配置已绑定 3,260 个互斥分配和当前名义角色探针。探针 4/4 实发成功，零重试，共 3,073 tokens。用户授权 B0 及新增开发批次的付费次数、金额均无上限，实际账单金额和币种待供应商回执。真实 selection 待教师资格，协议读回仅有 1/200 恢复、0 份机会证据；三份旧生成协议与当前冻结池均精确匹配 0/3,260。 [配置和账本核对](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-development-readiness-20261119/b0/step-report.md)

文档治理的 25 项问题已清零，8 项治理测试通过。三套历史冻结检出和安装包已迁至私有持久目录，原入口验证通过。主工作区 `config.py` 的一行改动已单独备份并恢复至 Git 基点。本轮先在研发分支交付，选定合入提交并完成同版回归及相对公开 main 的完整范围复审后，再合入 main。 [文档治理回执](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-development-readiness-20261119/governance/step-report.md) · [冻结迁移及 main 决定](../artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-freeze-directory-mode-20261119/step-report.md)

## 2026-10-04 历史分阶段开发状态

当前权威状态入口为 [current_authoritative_status.md](current_authoritative_status.md)。Phase 11 仿真工作台已接受，Phase 11.1 异步运行时已接受，Phase 11.2 Model Control Center 和 Simulation AI Console 已接受。Phase 12 是最终实验评估、论文证据整理和项目软件/仿真封板阶段。Phase 10 仍保持 `PHASE10_MOVEIT_DRY_RUN_ACCEPTED`、`PHASE10_2B_CONSOLE_ACCEPTED` 和 `PHASE10_LEVEL0_FRAMEWORK_ACCEPTED`；这些状态都没有发送真实硬件执行命令。

2026-10-04，T5夹爪修复已迁移到默认运行入口、模型工厂、启动环境、研究配置和任务语义证据。当前使用v2标定与[共用冻结包](../artifacts/research/process/20261004-gripper-project-migration/model-probe/model-frozen.json)；下文T3/T7冻结和在线指标属于历史验收时点。旧模型配置及原实验仍保留在各证据目录，不以新资产覆写。

当前按 [RGB-D 代理执行计划](superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)完成 T1/T2/T3/T6a/T4/T5：100/1000组静态数据、当前资产6/6类真实 MuJoCo 物理技能、20例离线教师各有独立验收。T3 的本地 Qwen3-VL 4B 经归一化坐标协议和顶抓几何适配，固定场景4/4通过并冻结；独立开发场景及拒答失败见[T3 验收](../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)，不代表在线抓取成功。T7 为 `DONE`：同 episode 真实闭环、三值验证、预算和独立数据作业已实现，v2 同 20 assignments 全保留，2 成功/18 失败/0 blocked/0 false completion（正常 2/12，全分配 10%）。[独立复算](../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)核对 34,353 样本、154 帧、52 动作，valid/accepted 均为 true；只限当前 MuJoCo 直立有色方块的开发 smoke，不是正式 G1。最终454项回归及30个源文件Ruff/mypy通过；T8/T17a 为 `READY`，T6b 保持 `TODO`。最新进度、变更、验证和交接见[过程文档](research/process/README.md)。目前没有新正式研究结果。

下表保留历史能力口径；MuJoCo 环境或旧运行时验收不能替代新 RGB-D 物理抓放验收。历史 full 已运行且 `PHASE12_REJECTED`，当前权威论文运行数为 0。

## 历史能力总表（截至 2026-10-04）

| 能力域 | 状态 | 验证入口 | 证据 | 运行环境 | 硬件声明 |
| --- | --- | --- | --- | --- | --- |
| 核心运行时 | 已验收 | `scripts/verify_phase6_2.py` | Phase 6.2 报告 | CI 可运行 | 不涉及硬件 |
| PCSC / ETEAC / AUTO | 已验收 | `scripts/verify_phase8_2.py` | Phase 8.2 产物 | CI 可运行 | 不涉及硬件 |
| MuJoCo | 已验收 | `scripts/verify_phase9.py` | `artifacts/phase9` | 本地仿真 | 不涉及硬件 |
| ROS 2 / MoveIt safety | 已验收 | `scripts/verify_phase9_1.py` | `artifacts/phase9_1` | ROS 2 / MoveIt 主机 | 不涉及硬件 |
| Isaac Sim | 已验收 | `scripts/verify_phase9_2.py` | `artifacts/phase9_2` | Isaac 主机 | 不涉及硬件 |
| 跨后端对比 | 已验收 | `scripts/run_phase9_2_cross_backend.py` | `artifacts/phase9_2/cross_backend` | MuJoCo + Isaac | 不涉及硬件 |
| Synthetic Dry-Run | 已验收 | `scripts/verify_phase10_1.py` | `artifacts/phase10/phase10_1` | CI 可运行 | 不涉及硬件 |
| MoveIt Runtime Dry-Run | 已验收 | `scripts/verify_phase10_moveit_dry_run.py` | `artifacts/phase10/moveit_dry_run` | ROS 2 / MoveIt 主机 | 不涉及硬件 |
| 仓库文档治理 | Phase 10.2A-R 后已验收 | `scripts/check_docs.py` | 文档和 CI 检查 | CI 可运行 | 不涉及硬件 |
| Simulation Workbench | Phase 11 已实现 | `scripts/verify_phase11_simulation_workbench.py` | `artifacts/phase11/verification` | CI 可运行，完整 E2E 需浏览器 | 不涉及硬件 |
| Simulation Runtime | Phase 11.1 已实现 | `scripts/verify_phase11_1_simulation_runtime.py --ci` / `--mujoco` / `--full` | `artifacts/phase11_1/verification` 和 `artifacts/phase11_1/runtime` | CI 跑 Mock 异步和恢复；MuJoCo runtime 需仿真环境 | 不涉及硬件 |
| Model Control Center | Phase 11.2 已接受 | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | CI 使用 fake provider/fake Ollama | 不涉及硬件 |
| Simulation AI Console | Phase 11.2 已接受 | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | planner dry-run，`dispatch=false` | 不涉及硬件 |
| Local Model Runtime | 尚未接受 | `scripts/verify_phase11_2_model_control.py --ollama` | 无 accepted evidence | 需要本地 Ollama 和已安装模型 | 不涉及硬件 |
| Phase 12 Final Evaluation | smoke pipeline ready；Phase 12.2 clean validation accepted；Ubuntu full 已运行但 PHASE12_REJECTED | `scripts/verify_phase12.py --smoke|--validation|--full` | `artifacts/phase12`、`artifacts/phase12_1/validation`、`artifacts/phase12_2/validation`、`artifacts/phase12_2_clean/validation`；完整新快照见权威状态 | 旧软件运行与公平物理评测分别验收 | 不涉及硬件 |
| 真实机械臂只读 | framework 已验收，真实设备未开始 | `scripts/verify_phase10_2c_level0.py --fake` | `artifacts/phase10/level0` | fake 模式 CI 可运行，hardware 模式现场专用 | 尚未声明真实只读验证 |
| 真实机械臂运动 | 未开始 | 无 | 无 | 现场设备 | 尚未声明运动验证 |

## 历史状态说明（截至 2026-10-04）

Phase 9.1 当时的结果是 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`，原因是 Isaac 和跨后端验证受环境限制。Phase 9.2 后续补齐 Isaac smoke、benchmark 和跨后端验证，形成 `PHASE9_2_ACCEPTED`。

Phase 10.2A 不改变 Phase 9.2 的结论，只补强 dry-run 证据和仓库治理。Phase 10.2B 增加控制台，Phase 10.2C 只完成 Level 0 fake/framework。真实机械臂验证仍是 `NOT_STARTED`。

Phase 11 从真实机械臂接入转向仿真工作台。`scenario_registry()` 和 `ExperimentConfig` 成为前后端实验配置的权威来源，Dashboard 不直接连接 MuJoCo、Isaac、ROS、MoveIt 或真实控制器。

Phase 11.1 解决 Phase 11 的同步运行限制：API 创建任务后立即返回 `QUEUED`，后台 worker 通过 SQLite lease 执行 allowlisted runner，并持久化 run、batch、event、metric、attempt、artifact 和 WebSocket replay sequence。MuJoCo READY 只表示环境可用；MuJoCo runtime accepted 必须通过 M11-01 至 M11-10。

Phase 11.2 增加模型控制中心和仿真 AI 控制台。OpenAI-compatible profile 和 Ollama 管理均通过安全后端 API；API key 不写入 artifact，真实 Ollama runtime 尚未接受，`installed_model_count=0`。

Phase 12 冻结 RQ1-RQ7 和 F01-F20，输出最终实验、统计、图表、表格、论文素材和答辩包。Baseline `7b4c9af` 的 90 条 smoke 记录是 `SYNTHETIC_PIPELINE_SAMPLE`，只能声明 `PHASE12_EXPERIMENT_SUITE_READY` 和 `PHASE12_THESIS_ASSET_PIPELINE_READY`，不能替代 validation 或 full。Phase 12.1 validation 从 actual software runners 产生 evidence；最早的 `artifacts/phase12_2/validation` provenance 为 `worktree_clean=false`，保留为 gap 证据。当前权威 validation evidence 是 `artifacts/phase12_2_clean/validation`：540 条 validation 记录中 466 条 runtime-completed，74 条在 runtime 前因 Isaac、MoveIt 或未配置模型环境阻塞，verifier 输出 `PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED` 和 `PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED`。只有 full profile 能声明 `PHASE12_FINAL_EVALUATION_ACCEPTED` 和 `PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED`。

## 2026-10-04 历史阻塞项

- 仓库内没有已授权的真实控制器配置。
- 还没有读取过现场急停或控制器状态。
- Level 0 真实硬件验收没有真实设备证据。
- 没有做过真实机械臂运动测试；MuJoCo 的 T4/T5 物理仿真已单独验收。

## 2026-10-04 历史下一阶段安排

T7 最终 runtime 竞态修复与454项回归已通过，T8/T17a 已 READY，下一步按依赖实施。现行模型使用 [T7 重探 4/4 后的新冻结目录](../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/)；历史 T3/T5 source freeze 不冒充现行源码，共享 capture 改动与 T5 12 份旧来源归档见 [preservation 清单](../artifacts/research/process/20261003-t7-visual-closed-loop/t5-prerequisite-preservation.json)。T8 先导、T6b 的 10000 组及教师整合尚未运行；95 runtime/277 prerequisite 测试只是阶段记录，最终合并回归为454 passed。随后开发两个优化方法并进行冻结评测。历史 Phase 12 保留为证据追溯。不得绕过后端直接控制硬件，也不能把仿真结论写成真实机械臂结论；真机相关开发保持冻结。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
