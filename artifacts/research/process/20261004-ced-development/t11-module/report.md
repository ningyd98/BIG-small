# T11 共同基线与模式CAS软件报告

状态：`SOFTWARE_IMPLEMENTED_PENDING_REVIEW_AND_RUNTIME_INTEGRATION`。本报告只登记软件实现与CPU回归；没有运行新selection、INITIAL、真实云请求、GPU渲染或正式研究，不代表T11研究验收完成。

## 实现

- 新增精确T11 `DecisionContext` 和 `RuntimeDecisionPolicy`。上下文绑定episode/frame/plan/command/mode版本；冻结视觉事实、条件测量、能力和校准动作概率映射，拒绝明确的oracle/未来故障字段与离线来源。
- `PeriodicPolicy`、`ThresholdPolicy`、`FrozenRuleAutoPolicy`消费全部既有事件，技能成功后仍复核证据，最终验证失败返回重新判断。共同安全/能力/原子边界/预算门在策略前执行。硬故障优先于缓存中的普通动作；重复事件不重复预留验证额度。策略无dispatch入口，LOCAL_RECOVER不参与基线。
- B0只接受0.5/1/2/5秒，并直接返回既有`PeriodicSupervision`；单在途、最新待发帧和原子阶段回复延期由原监督器实现。ticker计数被转为有界最新事件，另保留合并计数。
- B1只消费T9的`CONTINUE`动作校准概率；缺失、未知或非有限值只能重新观测或停止，不把总分/自报confidence当概率。
- B2冻结原RiskEvaluator/AutoModeSelector的实际源码hash、原policy全参数并直接调用原实现。追加可选`LegacyRuleEvidence`，仅供原规则需要的可观测缓存、合同、checkpoint和状态输入。缺失则不可用/STOP。保留旧decision中的legacy confidence字段兼容，但不作为校准概率或新判断provider概率。
- B0选择器从四个明确SELECTION目录重算全部120独立组、12层各10、静态40、物理结果与最终成本。检查唯一episode、assigned几何/固定区域、完整安全范围、结果分母、共同role/device/provider绑定和实际云请求总数；质量门为静态≥0.9、总体≥0.8、安全≤0.01，合格候选按云请求、平均完整墙钟耗时排序。缺证据保持INCOMPLETE，完整不合格为NO_FEASIBLE_BASELINE，禁止收益结论。
- 现有内存/SQLite仓储加入幂等prepare、checkpoint绑定、原子commit/abort。SQLite `BEGIN IMMEDIATE`在同一事务中读取真实当前版本并更新模式status与transition，跨连接不读过期镜像。COMMITTED/ABORTED不可回退，重复commit保留初次时间与switch_count。普通save_transition不能伪造COMMITTED。
- 严格research服务须有`ModeSwitchPolicySnapshot`和实时commit_guard。仓储事务内重算模式selection的全部120组物理/成本原始输入、transition/CAS顺序及checkpoint，校验source/policy身份，再调用实时guard并检查当前边界、确认次数、驻留/冷却和切换上限。无真实selection仍拒绝普通研究切换。B2模式参数固定原auto-v1，不借selection改写120秒/300秒/5次/2确认。硬STOP继续走独立安全路径。

## 验证

初始RED：38项失败，见`red.log`；另保存硬停止缓存、UNKNOWN、公开save伪提交、checkpoint model_copy绕过、模式日志缺证明及概率映射可变性的RED日志。实现和反例修复后，最终同一次CPU限定回归：**84 passed in 52.43s**，见`final-scoped.log`。涵盖本模块新测试、旧模式仓储、Phase 7 AUTO/API、Phase 8选择与原子边界、Phase 9安全切换，以及原独立监督器。全套仓库测试按协调者约束未运行，以免其他legacy测试真实调用模型/渲染。

最后Ruff：通过。mypy：5个源文件无问题，仅提示项目已有unused配置段。见`ruff.log`、`mypy.log`。

一次额外旧API检查暴露`test_transition_prepare_commit_abort_and_restart_recovery`：无外部仓储的历史独立service没有status而被新CAS拒绝，已修复并在最终84项回归通过。只对服务自建、非research内存仓储从prepare请求建立内部初始状态；外部仓储或research服务仍不推测当前状态。先前失败日志`legacy-extra.log`保留。

合成selection/物理fixture仅位于pytest临时目录，未计入真实研究分母。

## 协調裁定与集成

1. 为避免循环导入，DecisionContext在TYPE_CHECKING下引用T9/T10/预算类型；实际结构仍复用这些类。
2. 原B2需要的输入无法从T9轻量特征重建，协调者授权追加typed `legacy_rule_evidence`；其来源须由在线缓存/合同/状态适配器构建，禁止真值。
3. 严格研究提交构造：

```python
service = ModeTransitionService(
    repository=repo,
    clock=clock,
    commit_guard=current_boundary_from_real_checkpoint,
    require_verified_boundary=True,
    mode_switch_policy=verified_selection_snapshot,
)
prepared = service.prepare(request)
repo.save_transition_checkpoint(prepared.transition_id, checkpoint)
committed = service.commit(prepared.transition_id)
```

`ModeTransitionCheckpoint`字段为task_id、checkpoint_id、plan_version、command_seq、mode_version、atomic_action_active、confirmation_count、persisted_at。实时guard必须重读当前执行器状态与真实checkpoint；不能返回常量证明。由同一运行时所有者串行执行技能/模式提交。

4. `ModeSwitchPolicySnapshot`绑定method_id、policy_version、min_dwell_s、cooldown_s、max_switches、confirmation_count、当前`mode_switch_source_hashes()`、selection_directory及`mode-policy-selection.json`文件SHA256。后者schema为`ced.mode-selection.v1`/SELECTION，包含全候选candidate_id、directory、b0_period_s、parameters、source_hashes及selected_candidate_id。候选目录沿用pilot全原始文件，每case另含`mode-transition-events.json`，绑定参数/source，并含initial_last_switch_at、committed_transitions和逐次checkpoints。选出的所有候选必须共用assigned组和冻结角色；无原始资料的JSON或裸hash不能准入。
5. `selection-manifest.json`为SELECTION，字段period_s、snapshot_id、role_bundle_hash、device_pipeline_hash、edge_provider_hash、assignments_sha256、results_sha256。严格原始来源审计仍须由T8/角色冻结层校验实际模型请求与角色快照的对应，不能仅凭这些摘要hash宣称Max或完整方法验收。
6. RuntimeExperimentHarness.commit_mode_transition目前在service.commit后再次写status并+1 switch_count；协调者接入时应移除第二次状态更新，只读取仓储提交结果。API prepare endpoint目前每次建无repo临时service再save_transition，应改为`ModeTransitionService(repository=repo).prepare(...)`，避免跨请求uuid幂等冲突。以上共享集成文件按ownership未改。

## 后续真实验收

仍需共同role/设备/provider严格冻结绑定、实际B0/B1/B2配对selection、B1阈值选择、在线事件/原子边界/checkpoint的真实执行器接入，以及完整模式selection原始证据。当前baselines.yaml保留SOFTWARE_ONLY、selected period/threshold与选择hash均为空。INITIAL与正式研究均未发布。

归档：`baseline/`和`baseline-hashes.json`保存起点；`source/`和`source-hashes.json`保存19个实现/测试/依赖快照；`review-package.diff`只含8个own文件相对于任务起点的差异。没有commit/stage/push，也没有修改既有历史验收证据。


## Independent review corrections (2026-10-04)

The first independent review requested three fixes. The original released `source/`, `source-hashes.json`, `review-package.diff`, task-start baseline, and reviewer report remain intact. The corrected immutable snapshot is `review-fixed-source/` with `review-fixed-source-hashes.json`; changes against the first released snapshot are `review-fixed.diff`.

1. Both public repository save paths revalidate `model_copy` inputs and allow only an identical repeat of an existing PREPARED or terminal record. Task/from/to/versions/idempotency/decision/reason/prepared-time/transition-ID/hash cannot change under the old payload hash. Regression covers both in-memory and SQLite, original request retry and later commit still activating the original destination. Prepare also revalidates and rejects non-PREPARED admission.
2. Selection mode logs now require explicit `initial_current_mode` and integer `initial_mode_version`, and every transition must start from the current reconstructed mode/version. Initial mismatch, missing binding and impossible adjacent from/to chains reject. This adds required software evidence fields; no actual selection artifact was produced.
3. Policy duplicate caches now bind complete frozen online evidence, calibrated risk/action probabilities/bounds, features, calibration, condition values, network measurements, legacy B2 inputs, capabilities and budget limits/deadline. Spent counters remain mutable reservations and are not hashed. A changed duplicate event fails closed STOP without a second quota charge; a new UNKNOWN event uses budgeted REOBSERVE. Hard-stop/deadline checks still precede the cache.

RED: immutable CAS content 20 failures (plus two already rejecting invalid-enum cases); cache/initial/chain regressions six failures. GREEN: module tests 88 passed; final module plus related mode/API/supervision regression **115 passed in 62.63s**, exit 0, `review-final-scoped.log`. Two expected Pydantic serialization warnings occur for the intentionally invalid enum copied into the model; validation rejects it. Scoped Ruff and mypy both pass (five source files). Re-review remains pending; no physical/model/GPU/network/INITIAL/selection claims were enabled.
