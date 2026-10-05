# 验证矩阵

**当前新路径验收入口：** [云、边、端总计划](../../superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md)及[逐步阶段总结](continuation_20261004.md)。下表分列软件交付和真实未满足项；T8父任务保持IN_PROGRESS，边缘模型T12b后置。历史验证表保留原验收时点。

第56步：Astra补充计时依赖审计及四项新域任务；原10任务/48检查项保持历史编号。新75mm/X160mm标记唯一稀疏试验201帧全OBSERVED，旧189个UNKNOWN时刻全部恢复，12健康对照保留；稀疏最大间隔2.1167模拟秒，连续可见性仍未证明。R03真实RESET/120SETTLE及2缓存帧、488clock pair前缀VERIFIED；A收到包缺NONC被冻结协议拒绝，B跳过，UTC/current-time仍UNAVAILABLE。R07首组原件独审PROVEN、1/200；duration补修及共享原ledger的successor软件独审PASS，正式wall-Rcap守卫尚未实现。主线T12/18、T13并行，Max配置/九独立校准组/三消费者/G1和INITIAL/METHOD/FINAL未验收，边缘型号后置。 [第56步报告](../../../artifacts/research/process/20261004-ced-development/report-step56.md)；限定Git交付准备中，批量raw仍本地。

| 新执行单元 | 计划验证与原始证据 | 状态 |
|---|---|---|
| T3b | Max真实双图/结构化/拒绝，角色快照、载荷与未知摘要null；旧单模型绑定不可混用 | 软件独审PASS；当前key/profile缺失，新Max实测NOT_RUN |
| T7b | OpenCV身份、遮挡、抬升保持、完整物体范围/稳定性；新帧、无真值输入和真实动作 | 软件独审PASS；实际几何/运动与连续效果证据UNKNOWN |
| T8a | 固定机会原始标签重算；200故障实际注入后的独立可恢复性证明；四周期selection全分母 | 软件独审PASS；实际开发教师1组，完整正式来源/筛选未运行 |
| T8b | 新未用120组、完整轨迹/帧/成本/来源、合格B0及INITIAL | staged入口和资源补修复核中；实际新先导/INITIAL未成立 |
| T9—T12a | 校准/动作门/共同基线及同一DecisionJudge/CandidateSet，规则来源、能力与提交边界 | 软件独审PASS；实际校准/准入未成立，运行组合125项独审PASS |
| T13 | 持久恢复、完成阻塞、原子预算、最小修复和实际stage/resume/start | 多项软件PASS，接口继续集成；真实恢复/LOCAL_RECOVER未启用 |
| T15—T18 | 全分配、统计、只读页面、源档复现和真实研究 | 软件独审和浏览器3项PASS，实际CLI重建4200条软件记录一致；功效/FINAL/正式研究NOT_RUN |
| T12b | 后续型号影子无dispatch、独立selection、版本与基线回归；不设强制4B | TODO，后置选型 |

**2026-10-04 本轮更新：** T17a `DONE`；T8 `IN_PROGRESS`。软件最终合并518项通过，但全仓套件未完整通过。完整命令、原始日志、v1诊断与v2先导逐步汇入[阶段总结](continuation_20261004.md)；下文历史验收快照保留。

命令取自[执行计划](../../superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)，部分后续任务仍是待新增测试或CLI；列在此处不表示当前可运行。`TODO`表示未取得本轮验收证据；T1/T2/T6a/T3/T4/T5已在各自范围验收；T3仅固定S01和当前资产的限定几何门槛，T7为`DONE`且已完成v2开发smoke复算，最终454项回归通过；T8/T17a 为 `READY`，T6b仍为 `TODO`。软件通过只能证明相应代码契约，真实采集、模型和物理结果须分别出示原始证据。

| 任务 | 关键能力及证据层级 | 主要命令/检查 | 必需原始证据 | 状态 |
|---|---|---|---|---|
| T1 | 历史来源、分母与失败口径；SOFTWARE | `.venv/bin/python -m pytest -q tests/test_research_provenance.py tests/test_phase11_1_simulation_runtime.py` | 审计、回归日志、历史 5580 排除证明 | DONE；15项新单测，合并35项回归，独立复审通过 |
| T2 | 同状态 RGB/depth/mask、标定、session；SOFTWARE + REAL_CAPTURE | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_observations.py tests/test_rgbd_capture_session.py`；Phase9 MuJoCo 回归 | 原始三图、帧/时间/hash、≤5 mm 平面反投影、资源释放 | DONE；三 pass 同状态，100点最大误差2.728 mm，独立审查通过 |
| T3 | 真双图请求、严格解析、限定顶抓几何和模型冻结；SOFTWARE + REAL_CAPTURE + REAL_VLM | `scripts/probe_rgbd_model.py --config configs/research/model_qwen3vl_4b_normalized.yaml --output artifacts/research/process/20261003-t3-small-model-optimization/probe`；同输出目录加 `--verify-frozen` 只读复核 | [固定S01实测报告](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/probe-report.json)、[冻结快照](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/model-frozen.json)、[源码/参数/请求证据](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/model-frozen-evidence.json)、[完整验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md) | DONE；320×240 normalized_1000双图4/4，冻结复核VERIFIED；仅当前资产高5–10cm竖直方块，无物理执行；独立扩展不等于全场景通过 |
| T4—T5 | actuator/step 抓放；独立评价/教师；SOFTWARE + PHYSICS | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_physical_skills.py tests/test_rgbd_trajectory_dataset.py tests/test_rgbd_teacher_smoke.py`；`scripts/generate_rgbd_trajectories.py` 与 `scripts/validate_rgbd_trajectories.py` | [T4 v2真实六类验收](../../../artifacts/research/process/20261003-t4-physical-skills-v2/README.md)、[T5新协议20例与只读重评](../../../artifacts/research/process/20261003-t5-teacher-accepted/acceptance.md) | DONE；T4 6/6、T5 7成功/12失败/1安全，251项合并回归及独立复审通过 |
| T6a | 静态数据生产、原子写入、组划分；SOFTWARE + REAL_CAPTURE | 五份 `test_rgbd_dataset_{labels,integrity,splits,generation,export}.py`；已实现 generate/validate/export/replay CLI | 100/1000组 manifest、正负例/拒绝项、资源与分组审计 | DONE；124项数据测试通过；两批35正65负/301正699负，独立80/5/5/10及800/50/50/100，四入口均通过 |
| T6b | 全量数据与教师轨迹整合；REAL_CAPTURE + PHYSICS | 已有 `dataset_full.yaml`；T5已验收，待T8预算后运行10000组并整合教师 | 10000组manifest、轨迹、分组与实测预算 | TODO；未运行，不因配置已存在而验收 |
| T7 | 同episode反馈、三值验证、独立评分与作业；SOFTWARE + REAL_CAPTURE + REAL_VLM + PHYSICS | `tests/test_rgbd_closed_loop.py`、`tests/test_rgbd_online_verification.py`、`tests/test_rgbd_runtime_control.py`；已实现 `scripts/run_rgbd_smoke.py` | [v2 summary](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2/summary.json)、[独立复算](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)、新冻结包及运行终态证据 | DONE；同20场景2成功/18失败/0blocked/0falsecompletion，正常2/12，全分配10%；34,353样本/154帧/52动作，valid/accepted=true；最终454项回归通过 |
| T8 | 实际请求/字节账本、网络时钟与基础先导；REAL_CAPTURE + REAL_VLM + PHYSICS | 已实现研究测试、`run_rgbd_pilot.py` 与严格 `freeze_rgbd_protocol.py` | [v2报告](../../../artifacts/research/process/20261004-t8-foundation/foundation-v2-assessment.md)、279,482物理样本/1950帧/346请求；固定机会/200恢复证据仍缺 | IN_PROGRESS；v2全120组5成功、静态4/40；成本一致/在途0；质量门未过，初次冻结退出3 |
| T9—T10 | 校准风险与动作证据/B3；SOFTWARE + 实际来源记录 | `pytest` 的 `test_rgbd_risk_calibration.py test_visual_evidence_contract.py` | 分组隔离、校准图、固定机会 ID/UNKNOWN/误放行原始记录 | TODO |
| T11—T12 | 公平事件、B0/B1/B2、有限候选/provider；SOFTWARE + PHYSICS | `pytest` 的 `test_runtime_auto_baselines.py test_joint_visual_policy.py test_decision_judgment.py` | 成功后再判断、候选/概率语义/提交关联、拒答与完整账本、B0扫描 | TODO |
| T13 | 验证后恢复、有界预算、契约激活、局部修复/B4；SOFTWARE + PHYSICS | `pytest` 的 `test_visual_local_repair.py test_verified_recovery_lifecycle.py test_replan_activation.py` | 最终失败再路由、重启预算、ACK/启动区分、无重放、开发故障轨迹 | TODO |
| T15a、T16a | 分配/功效/统计与分母反例；SOFTWARE | `pytest` 的 `test_research_{assignments,runner,power,statistics,acceptance}.py` | 固定分配、零事件/失败/BLOCKED 反例、区间算法 | TODO |
| T17a/b | 数据与结果界面；SOFTWARE + 实际 E2E | 后端8项、前端30项及typecheck/lint/build；真实EGL/Chromium E2E3项 | [T17a验收](../../../artifacts/research/process/20261004-t17a-workbench/acceptance.md)：采集/模型不可用/取消后保留；T17b等待正式结果 | T17a DONE；T17b TODO |
| T15b/c、T16b | 最终冻结、正式物理评测、统计；REAL_CAPTURE + REAL_VLM + PHYSICS | 待实现 power/formal/gate-replay/analyze CLI | 独立 120 功效先导、最终 hash、N 全分母、200 故障、区间与负结果 | TODO |
| T18 | 原始记录重建、复现、回归；SOFTWARE + 小批 PHYSICS | 待在脚本目录实现 `reproduce_rgbd_research.py`；ruff/mypy/指定 pytest 与前端检查 | bundle hash、重建一致性、审查记录与限制 | TODO |
| T14（可选） | G5 三采样策略与域外；独立扩展 | 待实现训练 CLI、`test_targeted_rgbd_sampling.py` | 300 域外组×3 seed、同预算及模型 hash；未开展记 NOT_RUN | TODO/可选 |
| 判断 provider（可选） | Jev/其他模型影子与配对闭环；独立扩展 | 待实现 `test_optional_judge_provider.py`；T12可选对照协议 | 影子无dispatch、版本/候选/阈值、全成本、实际闭环与失败；未尝试为NOT_RUN | TODO/可选 |

阶段验收判据：G0 已发生阶段真实路径、泄露和跨集合组重复审计；G1 独立标称层；G2/G2a 对公平 B0；G3 固定机会回放且不冒充物理成功；G4 完整 200 故障；G5 独立扩展。目标数值、区间和统计规则以[研究设计](../../superpowers/specs/2026-10-03-rgbd-evidence-research-design.md)为准。`MOCK`、规划 dry-run、旧 Phase 记录、软件测试均不得填 PHYSICS 分子；硬件列始终 `NOT_STARTED`。

早期路线修订补充误完成率、UNKNOWN/拒答/回退率、端到端决策与故障响应延迟、无进展终止率；G2 云请求包含远程判断调用。后续任务仍为 TODO；T7 已实现范围与本轮证据以上表为准，不将文档检查当作产品验收。

T6a最终证据：[验收报告](../../../artifacts/research/process/20261003-t6a/acceptance.json)、[100组校验](../../../artifacts/research/process/20261003-t6a/smoke-validate.json)、[1000组校验](../../../artifacts/research/process/20261003-t6a/validation-validate.json)、[1000组CLI审计](../../../artifacts/research/process/20261003-t6a/validation-cli-audit.json)、[1000组资源](../../../artifacts/research/process/20261003-t6a/validation-resources.json)、[独立代码审查PASS](../../../artifacts/research/process/20261003-t6a/final-review.md)。定向Ruff/mypy（18文件）和123项旧路径回归通过；T6a已关闭，T6b仍TODO。

T3软件与扩展验证：225项相关回归、6个source文件mypy通过，独立审查无阻断项。两批独立开发场景共32个唯一scene/RGB，29/32符合各自判据：有目标定位23/24、目标缺失明确拒绝6/8。两条缺失幻觉几何阻断和一条有目标误拒绝均为0步契约，`all_cases_pass=false`；无error/missing/duplicate，未调整阈值。该结果不替代T7闭环或PHYSICS，详见[本轮验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)。


## 2026-10-04 T7 证据与剩余质量门

当前[T7证据目录](../../../artifacts/research/process/20261003-t7-visual-closed-loop/)保存v1/v2完整分配、源码快照、新模型冻结、逐帧观测、动作和独立物理样本。v1复算valid=true、accepted=false；v2复算valid=true、accepted=true，20分配全保留，2成功/18失败/0blocked/0falsecompletion（正常2/12，全分配10%）。两者均formal_g1=false，不以开发smoke替代正式G1。

95项runtime和277项prerequisite回归属于阶段证据；最终454项回归已通过，30个相关源文件Ruff/mypy通过。独立数据job已真实完成1组、0模型调用、task_success=false。历史T3冻结复核和T5来源校验仅绑定原源码时点；现行模型使用[T7重探4/4后的目录](../../../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/)，T5历史12份来源与当前共享capture差异见[preservation](../../../artifacts/research/process/20261003-t7-visual-closed-loop/t5-prerequisite-preservation.json)，其余11份源码及物理判据未变。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../../../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
