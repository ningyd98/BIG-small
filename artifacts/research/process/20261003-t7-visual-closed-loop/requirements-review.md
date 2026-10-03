# T7 逐项需求复审

审查日期：2026-10-04（Asia/Shanghai）。只读核对 [路线图 Task 7](../../../../docs/superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md) 与 [设计 §4](../../../../docs/superpowers/specs/2026-10-03-rgbd-evidence-research-design.md)。未修改源码或状态文档，未启动 GPU/模型请求。

**独立审查时点结论（最终关闭证据见文末 Root 核对）：已找到 T7 各项必需能力的实现、对应测试及要求的开发 smoke 真实证据；未发现新的必须实现项。最终 worker 发布异常处理与根任务最终回归尚待核验，T7 继续为 IN_PROGRESS，不能据本报告标 DONE。**

## 要求映射

下表源码路径均相对 `src/cloud_edge_robot_arm/`，测试路径相对 `tests/`。“已有覆盖”不代表正在进行的最终全回归已完成。

| Task 7 / 设计要求 | 实现与测试 | 实际证据 / 状态 |
| --- | --- | --- |
| 借用 session 不 initialize/reset/shutdown；owner 释放 | `vision/capture.py`；`test_rgbd_shared_capture.py` 的 shared backend、正常/异常退出和采集异常用例；保留自建 session 旧路径 | 已有覆盖；v2 逐例观测与动作绑定同 episode。 |
| 动作后新帧，旧图裁剪不算重观测 | `execution._VisualEpisode.recapture` 检查 episode、frame、采集时间；`test_moved_target_requires_new_frame` | [v2复算](smoke-20-v2-validation.json)逐例核对154帧和52动作。 |
| 三值条件；缺时间、深度、身份或未注册条件不放行；释放不证明放置 | `edge/evidence/conditions.py`、`edge/runtime/condition_evaluator.py`、`edge/completion_evaluator.py`；`test_rgbd_online_verification.py` 覆盖 visibility/height、unknown/timestamp、release/placement、completed marker、身份与深度反例 | 已有覆盖；ONLINE_VERIFICATION 与三层结果保留在每个 episode。 |
| 复用已有技能与 SafetyShield，不以真值驱动物理执行 | `execution.py` 经 `SkillExecutor`/registry 和 SafetyShield 前后检查；显式 RGB-D 目标、负关节速度、安全上升测试 | [执行复审](execution-final-review.md)、v2物理逐步证据；未修改T4/T5物理判据。 |
| 事件、UNKNOWN重观测、失败先路由、无能力不选择恢复 | `auto_mode/runtime_events.py`、`edge/recovery/verification_router.py`；final unknown、failure routes、missing recovery、hard safety tests | 已有覆盖；T7只开放已实现能力，LOCAL_RECOVER等后续能力不被伪造。 |
| 有界次数、无进展及绝对截止时间；耗尽后不能PASS复活 | `VerificationBudget/State`、路由及checkpoint；`test_retry_exhaustion_is_terminal_even_if_later_call_claims_pass`、无进展/重建用例 | `configs/research/visual_smoke.yaml`预算2/0/3/120；每次预算前后值和event ID入证据。完整恢复生命周期属于T13。 |
| 模型取消/超时、晚到结果无dispatch；独立心跳与HTTP/WS共factory | `vision/request_control.py`、runtime worker/dispatcher及API工厂；`test_rgbd_runtime_control.py` 的迟到返回、deadline、独立heartbeat、WS-first、终态竞态用例 | 实现和阶段测试已存在；**最终worker发布I/O异常处理及全部终态一致性回归待核**。 |
| 默认RGBD/VISUAL_PLANNING，三scope明确；无模型可采集；规划不算任务成功 | `simulation_workbench/models.py`、`simulation_runtime/worker.py`；scope默认、capture without model、missing model保留相机证据的测试 | 已有覆盖；缺模型明确BLOCKED，CAPTURE_ONLY/VISUAL_PLANNING不声明task_success。 |
| DATASET_GENERATION独立job_type，无模型、受限路径与取消 | `simulation_runtime/dataset_job.py`复用generator；`test_rgbd_dataset_job.py`检查schema round-trip、scope/模型路径、symlink拒绝、状态与取消callback | [真实数据job](data-job-real/verification.json)：1组COMPLETE/SUCCEEDED、0模型调用、task_success=false、consistent=true。最终worker发布质量门仍单列。 |
| offline selection/test接口、原始时间戳、独立定位参照与全分母 | `vision/evaluation.evaluate_model`、`scripts/evaluate_rgbd_model.py --split selection/test`；split audit选择，先plan后读取instance评分；`test_offline_evaluation_uses_labels_only_after_online_request`实际覆盖test分支及20mm误差反例 | [真实selection摘要](offline-selection/derived-summary.json)：5分配、1通过、0blocked、识别覆盖4/5；定位误差相对离线刚性方块顶面中心。test接口有CPU覆盖，未宣称已运行正式test集。 |
| online/oracle隔离，在线与独立物理共同决定成功 | `execution.run_visual_episode`在在线终止后首次调用独立evaluator；`combine_outcome`合取；oracle不改变routing、explicit TCP无truth和false done测试 | v2逐例保存online/physical；smoke在末尾额外做独立assignment语义判定，`semantic_used_for_online_routing=false`。 |
| 20独立开发场景包含正常完成和预分配失败，保留分母且不冒充G1 | `run_rgbd_smoke.py`先写assignments，测试拒绝全失败通过、保留模型缺失全部分配、固定20个独立scene hash | [v2摘要](smoke-20-v2/summary.json)：20/20保留，2正常成功、18失败、0blocked、0falsecompletion；正常2/12，全分配10%。[复算](smoke-20-v2-validation.json)34,353样本/154帧/52动作，valid/accepted=true、errors=[]、formal_g1=false。 |

## 边界与待核项

- 真实模型前置已在 [T7新目录](model-probe/probe-report.json)重探4/4并冻结；旧T3包不能当作现行source freeze。[T5历史来源保存](t5-prerequisite-preservation.json)记录12份旧来源，仅共享capture与当前不同，其余11份源码和物理判据未变。
- v1全20失败、34份源码快照与22,147样本/105帧/33动作保留；[v1复算](smoke-20-v1-validation.json)是valid=true、accepted=false。v2成功不删除或重写v1失败。
- 离线`invalid_depth_rejection_rate`当前含义是深度拒绝数除以全部分配样本，真实selection为3/5；不是无效深度样本召回率，也不是物理成功率。
- 计划提到teacher在线字段为None；实现选择保留T5原序列化、不添加在线字段，由`VisualEpisodeOutcome`扩展在线结果，测试明确要求旧teacher结构不变。该兼容差异符合本轮保留T5源码/历史证据的约束，teacher不计在线成功分母。
- 设计§4.2—4.5中的校准风险、完整决策身份、成本候选provider、局部修复和云边ACK/启动协调按路线归属T9—T13；T7只交付基础事件、验证与有界停止，不把这些后续功能当作已完成。
- 必须等待根任务核验最终worker发布I/O异常不虚报成功，以及完整最终suite与终态产物一致性。95 runtime/277 prerequisite是阶段数字；本报告不填写最终总数，也不关闭T7或提前放行T8/T17a。

当前支持范围仍是校准MuJoCo资产、直立有色方块。语义尾评分防止错误任务被计为成功，但不保证阻止评分前的wrong-object动作；未验收任意自然语言、多目标或正式G1。无真实硬件、10000组数据或commit/push声明。


## Root 最终证据核对（2026-10-04）

以上待核项现已关闭：最终worker发布I/O异常的瞬时/持续失败与换主反例已通过[运行时独审](runtime-final-review.md)；[完整回归](final-tests.log)454 passed、无排除，30源Ruff/mypy通过。[真实worker](worker-closed-real-v3/verification.json)终态一致、error=null、integration_valid=true，任务实际FAILED保持不变。T7现为DONE，T8/T17a为READY，T6b仍TODO；范围与失败分母见[验收](acceptance.md)。保留上文作为该独立需求审查时点记录。
