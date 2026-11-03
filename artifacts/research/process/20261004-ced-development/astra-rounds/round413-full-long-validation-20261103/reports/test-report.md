# R413 全量长测测试报告

执行收口，整体未全部通过；不能据此宣布正式研究验收通过。报告包含失败、跳过、未完成和外部未运行项，没有以软件通过替代真实实验。

被测分支 `research/20261004-continuation`，代码提交 `ab18abd0f82a024b62f4423c946c6585f8d18c65`；官方 real_robot 源码指纹 `3bfb7dbb8036b8389fa9a9bccdb2e961a1fd225be2d42b511539044e944995f4`。

运行区间：2026-11-03 18:11:58—2026-11-03 23:08:22（北京时间）；全流程墙钟 17783.674 秒（4.940 小时）。UTC 起止为 `2026-11-03T10:11:58.963126+00:00` / `2026-11-03T15:08:22.637110+00:00`。

## 1. 范围与方法

一次新采集得到4753个唯一节点、288个模块，collection error=0；4751软件节点与2个真实数据节点分开登记。相对旧4732清单增加21项，旧节点未丢失。软件节点按关键长node及其余模块隔离进程执行，不能等同于单一pytest进程的全套共享状态运行。

所有4751软件节点STARTED各一次，重复启动0。只有事件明确未开始的节点才允许尾部接续；已开始且未完成者不重跑。原始测试顺序、断言、产品TTL/timeout/并发策略、模型与硬件门禁保留。默认模块1800秒，可信未开始尾部每项600秒；UTC每后端7200秒；其它长节点与闭环按各自冻结spec额度执行；浏览器默认600/研究300秒；Phase12 full14400秒、后续每阶段1800秒，owned清理上限30秒。额度是上限，不是性能验收线或等待时长预测。

| 范围 | 本轮结果 | 含义 |
| --- | --- | --- |
| Python采集 | 4753唯一节点 / 288模块 / 0采集错误 | 比旧4732清单增加21项，未丢旧节点 |
| 软件节点 | 4709 PASS / 35 FAIL / 6 SKIP / 1 INCOMPLETE | 4751项均STARTED一次；不以未完成或skip冒充通过 |
| 真实数据节点 | 2 NOT_RUN_EXTERNAL_DATA | robomind / graspclutter6d实际数据未运行 |
| 关键闭环 | 94 PASS，另9项关键回归PASS | 9个T3长节点+85闭环节点；关键9项含native队列与模式兼容 |
| 浏览器 | 42 PASS / 1 原有SKIP | 旧19项全部PASS；cleanup=True |
| 前端开发 | Vitest43 PASS；app/node类型、ESLint、构建PASS | Prettier与API生成一致性检查FAIL |
| Phase12 full | 5580结果行；verifier=PHASE12_REJECTED | 登记行、raw声明、内层真实回执、正式验收分别统计 |

JUnit确认4737个Python节点。原075被1800秒预算终止，14个已开始节点没有该模块的JUnit终态文件：其中11项三阶段PASS、2项call FAIL、1项INCOMPLETE。完整阶段事件、真实exit、source和清理记录仍在；不能补造JUnit或把原模块写成整组PASS。6项backend参数化skip是原测试行为，2项外部数据NOT_RUN不是skip。详情见[唯一覆盖总账](coverage-ledger.json)及[Python收口记录](python-outcomes.json)。

## 2. 关键闭环与长节点

原生开发MOCK队列5项与默认模式兼容4项通过，另94项闭环全部通过；它们均已包含在4751分母内，不额外加总。原生队列运行如下，结束后租约释放、heartbeat线程与run SQLite FD均无残留：

| 开发运行 | 终态 | 耗时/秒 | attempt |
| --- | --- | --- | --- |
| r399-native-eteac | SUCCEEDED | 1.475165 | 1 |
| r399-native-pcsc | SUCCEEDED | 1.610095 | 1 |

完整T3九项均三阶段PASS、source一致、owned回收；原五个失败目标全部执行到断言并通过：

| 阶段 | 原节点 | call/秒 | 阶段/秒 | 结果 |
| --- | --- | --- | --- | --- |
| py-t3-01 | tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[memory] | 2267.121787 | 2268.879781 | PASS |
| py-t3-02 | tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[sqlite] | 2231.852229 | 2233.628963 | PASS |
| py-t3-03 | tests/test_operational_runtime_closure.py::test_private_startup_to_transaction_grounding[memory] | 235.721469 | 237.409238 | PASS |
| py-t3-04 | tests/test_operational_runtime_closure.py::test_private_startup_to_transaction_grounding[sqlite] | 232.889059 | 234.246918 | PASS |
| py-t3-05 | tests/test_operational_runtime_closure.py::test_b_terminal_publication_confirmation_fault[commit_close] | 235.184971 | 236.852386 | PASS |
| py-t3-06 | tests/test_operational_runtime_closure.py::test_b_terminal_publication_confirmation_fault[confirm_timeout] | 230.590333 | 232.312394 | PASS |
| py-t3-07 | tests/test_operational_runtime_closure.py::test_b_terminal_publication_confirmation_fault[prior_bound] | 228.035153 | 229.634919 | PASS |
| py-t3-08 | tests/test_operational_runtime_closure.py::test_b_public_confirmed_publication_control[memory] | 232.664142 | 234.294247 | PASS |
| py-t3-09 | tests/test_operational_runtime_closure.py::test_b_public_confirmed_publication_control[sqlite] | 216.080496 | 217.753899 | PASS |

UTC两后端合计4502.508744秒，原合计600秒性能门槛**未达到**。测试使用局部UTC跳变±一天和late-return拒绝场景，没有调整宿主时钟。耗时包含该测试自身观测逻辑与共享主机条件，不直接等同生产延迟；本轮没有追加profile来确证性能归因。9项T3阶段合计6125.012745秒。[UTC核验](utc-audit.json)、[T3核验](t3-audit.json)、[原生队列核验](native-queue-audit.json)保留精确证据SHA。

## 3. 软件失败与验证空缺

| 类别 | 失败数 | 证据解释 |
| --- | --- | --- |
| 测试替身接口不一致 | 21 | RuntimeSpy缺少_local_mode，21项在check_active处失败，目标capture/plan/supervision断言未得到有效验证。 |
| 回调签名不一致 | 1 | post安全门场景的recapture测试lambda不接受completion关键字，不能据此宣称实际安全门已验证。 |
| 租约交接并发/授权 | 5 | 3项嵌套public mutation授权拒绝、1项database is locked、1项跨进程Queue.Empty；产品与测试注入前置的根因尚待分离。 |
| 运行回执与验收契约 | 2 | F20计数应1实际0；另一项期望accepted实际evidence-gaps。内层BLOCKED_BY_ENV而外层宣称SUCCESS需要优先处理。 |
| 事件轨迹复现性 | 2 | 两项相同配置/seed的result_hash比较通过，事件摘要或payload_hash不一致；具体差异字段未通过额外重跑定位。 |
| 中文规范与覆盖 | 4 | 29+9+2个公共文档字符串缺口，及2330个tracked代码路径未纳入默认审计；这是被测ab18基线下的计数。 |

RuntimeSpy的21项与recapture的1项属于已观测到的测试接口不匹配：失败发生在目标检查前，不能作为目标行为已经验证、或21个生产缺陷的证明。租约组5项则仍需区分测试注入契约与真实并发实现；本轮不通过放宽嵌套写入授权、替换锁或改断言来消除失败。

F20新鲜证据显示，默认RGBD使MOCK任务报RGBD_CAMERA_REQUIRED、task_execution=NOT_RUN、内层BLOCKED_BY_ENV，外层适配器却声称成功。证据和静态源码链见[f20-receipt-audit.json](f20-receipt-audit.json)以及[evidence/f20-first-duplicate-result.json](evidence/f20-first-duplicate-result.json)。这是回执真实性缺口；不是新增一次修复后的GREEN运行。旧R373对应F20节点是NOT_COMPLETED，不能称本轮从旧PASS回归。

两项复现性失败的result_hash比较通过，但过滤后的event digest或payload_hash序列不同；完整差异payload没有由原测试导出为JSON。本轮未为补证再次运行或额外打开其运行SQLite。已保留现有失败及本地DB文件SHA，根因尚未确定。

35项失败逐项如下；完整longrepr、三阶段耗时及原日志位置保存在总账/Python收口记录，表中只截取首个失败证据摘要：

| 序号 | 节点 | 分类 | 原失败摘要 | 阶段 |
| --- | --- | --- | --- | --- |
| 1 | `tests/test_chinese_comment_checker.py::test_auto_mode_public_api_has_chinese_docstrings` | CHINESE_DOCSTRINGS_AND_AUDIT_SCOPE | E   AssertionError: assert ['src/cloud_e...actions', ...] == [] / E      / E     Left contains 29 more items, first extra item: 'src/cloud_edge_robot_arm/auto_mode/baseline_policies.py:300:choose' / E     Use -v to get more diff | py-module-005 |
| 2 | `tests/test_chinese_comment_checker.py::test_contracts_public_api_has_chinese_docstrings` | CHINESE_DOCSTRINGS_AND_AUDIT_SCOPE | E   AssertionError: assert ['src/cloud_e...ty_hash', ...] == [] / E      / E     Left contains 9 more items, first extra item: 'src/cloud_edge_robot_arm/contracts/models.py:580:replan_payload_hash' / E     Use -v to get more diff | py-module-005 |
| 3 | `tests/test_chinese_comment_checker.py::test_simulation_workbench_public_api_has_chinese_docstrings` | CHINESE_DOCSTRINGS_AND_AUDIT_SCOPE | E   AssertionError: assert ['src/cloud_e..._is_separate'] == [] / E      / E     Left contains 2 more items, first extra item: 'src/cloud_edge_robot_arm/simulation_workbench/models.py:268:PublicationStatusView' / E     Use -v to get more diff | py-module-005 |
| 4 | `tests/test_chinese_comment_checker.py::test_default_paths_cover_all_tracked_code_files` | CHINESE_DOCSTRINGS_AND_AUDIT_SCOPE | E   AssertionError: assert [PosixPath('d...n.json'), ...] == [] / E      / E     Left contains 2330 more items, first extra item: PosixPath('dashboard/playwright.research.config.ts') / E     Use -v to get more diff | py-module-005 |
| 5 | `tests/test_phase12_2_runtime_authenticity.py::test_f20_uses_real_phase11_runtime_receipts` | PHASE12_RECEIPT_AND_ACCEPTANCE_CONTRACT | tests/test_phase12_2_runtime_authenticity.py:304: in test_f20_uses_real_phase11_runtime_receipts /     assert receipt["duplicate_competition_evidence"]["runner_invocation_count"] == 1 / E   assert 0 == 1 | py-module-075 |
| 6 | `tests/test_phase12_2_runtime_authenticity.py::test_paired_summary_marks_isaac_blocked_as_not_accepted` | PHASE12_RECEIPT_AND_ACCEPTANCE_CONTRACT | E   AssertionError: assert 'PHASE12_VALI...EVIDENCE_GAPS' == 'PHASE12_VALI...ENTS_ACCEPTED' / E      / E     - PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED / E     + PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS | py-module-075 |
| 7 | `tests/test_phase8_1_reproducibility.py::test_same_config_and_seed_reproduce_result_and_event_trace` | EVENT_TRACE_REPRODUCIBILITY | E   AssertionError: assert '380b45cf9b0a...32f80b8af41d9' == 'f083e50e3b86...f80fb8010188a' / E      / E     - f083e50e3b86106108784429c7502e27dc625e97b8fd002767af80fb8010188a / E     + 380b45cf9b0ad8b8d4019af2118b02d0c4a5f1136f72c58fe6332f80b8af41d9 | py-module-114 |
| 8 | `tests/test_phase8_reproducibility.py::test_same_config_and_seed_produce_same_result_hash_and_events` | EVENT_TRACE_REPRODUCIBILITY | E   AssertionError: assert ['07b33c39d5c...1a672a5', ...] == ['07b33c39d5c...1a672a5', ...] / E      / E     At index 3 diff: 'bd1bfbe3288d5df3f759aa2af3965768a9d6d5839719c4dd669b0edb67c80ff0' != '4ad5e0877f34b23f0fca81951809b24c478457928f974d6fb11a6a300e086548' / E     Use -v to get more diff | py-module-129 |
| 9 | `tests/test_rgbd_closed_loop.py::test_negative_joint_overspeed_rejected_at_actual_execution_gates[post]` | RECAPTURE_CALLBACK_SIGNATURE_DRIFT |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ / src/cloud_edge_robot_arm/vision/execution.py:1372: in execute /     self.recapture(completion=completion) / E   TypeError: _safety_gate_run.<locals>.<lambda>() got an unexpected keyword argument 'completion' | py-module-215 |
| 10 | `tests/test_rgbd_lease_handoff.py::test_publication_guard_is_cross_process_and_repository_reentrant` | LEASE_HANDOFF_CONCURRENCY_OR_AUTHORITY |            ^^^^^^^^^^^^^^^^^^^^ / /usr/lib/python3.12/multiprocessing/queues.py:114: in get /     raise Empty / E   _queue.Empty | py-module-229 |
| 11 | `tests/test_rgbd_lease_handoff.py::test_expiry_scan_cannot_interrupt_a_replacement_lease` | LEASE_HANDOFF_CONCURRENCY_OR_AUTHORITY |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ / src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py:2043: in _writer_call /     raise OperationalLeaseError( / E   cloud_edge_robot_arm.simulation_runtime.operational_lease.OperationalLeaseError: nested public mutation is not a registered same-job subordinate | py-module-229 |
| 12 | `tests/test_rgbd_lease_handoff.py::test_expiry_scan_rechecks_current_expiration_in_atomic_update` | LEASE_HANDOFF_CONCURRENCY_OR_AUTHORITY |     updated = self.update_status_cas( / tests/test_rgbd_lease_handoff.py:500: in refresh_before_cas /     connection.execute( / E   sqlite3.OperationalError: database is locked | py-module-229 |
| 13 | `tests/test_rgbd_lease_handoff.py::test_cancel_racing_handoff_cancels_current_job_without_restoring_old_owner` | LEASE_HANDOFF_CONCURRENCY_OR_AUTHORITY |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ / src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py:2043: in _writer_call /     raise OperationalLeaseError( / E   cloud_edge_robot_arm.simulation_runtime.operational_lease.OperationalLeaseError: nested public mutation is not a registered same-job subordinate | py-module-229 |
| 14 | `tests/test_rgbd_lease_handoff.py::test_stale_retry_snapshot_cannot_requeue_new_owner` | LEASE_HANDOFF_CONCURRENCY_OR_AUTHORITY |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ / src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py:2043: in _writer_call /     raise OperationalLeaseError( / E   cloud_edge_robot_arm.simulation_runtime.operational_lease.OperationalLeaseError: nested public mutation is not a registered same-job subordinate | py-module-229 |
| 15 | `tests/test_visual_worker_execution.py::test_initial_capture_is_claimed_before_real_effect_and_completed_after_source_recheck` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 16 | `tests/test_visual_worker_execution.py::test_unavailable_capture_claim_prevents_sensor_read` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 17 | `tests/test_visual_worker_execution.py::test_capture_failure_keeps_spent_claim_and_has_no_completion` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 18 | `tests/test_visual_worker_execution.py::test_source_loss_during_capture_does_not_complete_or_install_frame` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 19 | `tests/test_visual_worker_execution.py::test_plan_claim_surrounds_provider_and_durable_completion_replaces_memory_route` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 20 | `tests/test_visual_worker_execution.py::test_durable_deadline_is_not_restarted_by_episode_or_source_check` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 21 | `tests/test_visual_worker_execution.py::test_canonical_worker_route_uses_current_checkpoint_context_not_role_digest` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 22 | `tests/test_visual_worker_execution.py::test_source_route_cannot_authorize_native_unknown_action[STOP]` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 23 | `tests/test_visual_worker_execution.py::test_source_route_cannot_authorize_native_unknown_action[CONTINUE]` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 24 | `tests/test_visual_worker_execution.py::test_dispatch_guard_rejects_cleared_source_binding_before_executor` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-279 |
| 25 | `tests/test_visual_worker_supervision_execution.py::test_supervision_capture_and_plan_are_claimed_on_owner_before_provider` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 26 | `tests/test_visual_worker_supervision_execution.py::test_missing_periodic_capture_claim_prevents_camera_read` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 27 | `tests/test_visual_worker_supervision_execution.py::test_initial_plan_wait_checks_owned_claim_and_records_wait_purpose` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 28 | `tests/test_visual_worker_supervision_execution.py::test_missing_owned_plan_wait_claim_stops_before_physics` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 29 | `tests/test_visual_worker_supervision_execution.py::test_supervisor_provider_uses_owned_frame_without_backend_access` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 30 | `tests/test_visual_worker_supervision_execution.py::test_supervision_result_completed_once_or_stopped_when_source_changed[False]` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 31 | `tests/test_visual_worker_supervision_execution.py::test_supervision_result_completed_once_or_stopped_when_source_changed[True]` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 32 | `tests/test_visual_worker_supervision_execution.py::test_changed_supervisor_wire_context_stops_instead_of_discarding_as_old_state` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 33 | `tests/test_visual_worker_supervision_execution.py::test_discard_rechecks_ttl_before_recording_its_owned_reason[EXPIRED]` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 34 | `tests/test_visual_worker_supervision_execution.py::test_discard_rechecks_ttl_before_recording_its_owned_reason[CURRENT]` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |
| 35 | `tests/test_visual_worker_supervision_execution.py::test_supervisor_reobservation_waits_for_owned_fresh_effect_frame` | RUNTIME_SPY_INTERFACE_DRIFT | src/cloud_edge_robot_arm/vision/execution.py:713: in check_active /     if runtime is not None and runtime._local_mode: /                                ^^^^^^^^^^^^^^^^^^^ / E   AttributeError: 'RuntimeSpy' object has no attribute '_local_mode' | py-module-283 |

唯一INCOMPLETE节点为 `tests/test_phase12_2_runtime_authenticity.py::test_verifier_rejects_runtime_gap_when_runtime_receipt_missing`。它已STARTED，故没有进入38个未启动尾部的接续队列；本轮没有取得其call/teardown终态。

六项原有backend参数化跳过：

| 节点 | 原skip原因 |
| --- | --- |
| tests/test_visual_bootstrap_repository.py::test_sqlite_write_failure_rolls_back_whole_bootstrap_transition[memory] | ('/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_visual_bootstrap_repository.py', 357, 'Skipped: SQLite storage failure regression') |
| tests/test_visual_bootstrap_repository.py::test_promotion_storage_failure_rolls_back_bootstrap_and_all_owner_rows[memory] | ('/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_visual_bootstrap_repository.py', 787, 'Skipped: SQLite transaction failure') |
| tests/test_visual_owner_repository.py::test_sqlite_failure_after_candidate_writes_rolls_back_entire_initial_group[memory] | ('/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_visual_owner_repository.py', 421, 'Skipped: SQLite transaction failure only') |
| tests/test_visual_owner_repository.py::test_two_memory_publishers_race_only_one_revision_and_checkpoint[sqlite] | ('/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_visual_owner_repository.py', 487, 'Skipped: memory concurrency case; SQLite distinct connection case below') |
| tests/test_visual_owner_repository.py::test_two_sqlite_boundary_publishers_one_committed_revision[memory] | ('/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_visual_owner_repository.py', 507, 'Skipped: SQLite distinct connections only') |
| tests/test_visual_verification_repository.py::test_sqlite_insert_failure_rolls_back_pool_publication_and_claim[memory] | ('/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_visual_verification_repository.py', 471, 'Skipped: SQLite trigger covers transactional persistence; memory pre-encodes rows') |

两个真实数据节点：`tests/test_external_rgbd_real.py::test_actual_loader_and_offline_provider[robomind]` 与 `[graspclutter6d]`，均为NOT_RUN_EXTERNAL_DATA；未下载数据或以fixture代替实际数据验收。

## 4. 静态、前端、浏览器与实验步骤

共22个非Python步骤；该表使用原阶段returncode与terminal，不把controller循环正常结束误写成所有检查通过：

| 阶段 | 状态 | exit | 耗时/秒 | JUnit |
| --- | --- | --- | --- | --- |
| browser-default | PASSED | 0 | 115.254996 | {"PASSED": 39, "SKIPPED": 1} |
| browser-research | PASSED | 0 | 22.803102 | {"PASSED": 3} |
| dashboard-api | FAILED | 1 | 3.685604 | {} |
| dashboard-build | PASSED | 0 | 1.614533 | {} |
| dashboard-eslint | PASSED | 0 | 2.134214 | {} |
| dashboard-prettier | FAILED | 1 | 1.614943 | {} |
| dashboard-type-app | PASSED | 0 | 2.646402 | {} |
| dashboard-type-node | PASSED | 0 | 1.102519 | {} |
| dashboard-vitest | PASSED | 0 | 17.631341 | {"PASSED": 43} |
| phase12-analysis | PASSED | 0 | 1.618254 | {} |
| phase12-export | PASSED | 0 | 0.579649 | {} |
| phase12-full | PASSED | 0 | 5024.445008 | {} |
| phase12-verify | FAILED | 1 | 7.282992 | {} |
| static-comments | FAILED | 1 | 1.609972 | {} |
| static-compile | PASSED | 0 | 1.617647 | {} |
| static-contracts | PASSED | 0 | 0.580373 | {} |
| static-docs | FAILED | 1 | 0.579853 | {} |
| static-mypy | FAILED | 2 | 0.581440 | {} |
| static-pip | PASSED | 0 | 1.095698 | {} |
| static-ruff-check | FAILED | 1 | 0.584038 | {} |
| static-ruff-format | FAILED | 1 | 0.583604 | {} |
| static-secrets | PASSED | 0 | 2.642499 | {} |

非Python失败阶段：dashboard-api, dashboard-prettier, phase12-verify, static-comments, static-docs, static-mypy, static-ruff-check, static-ruff-format。

- Ruff check：1156条诊断、42文件；按代码分布 `{"E501": 1000, "I001": 94, "F401": 3, "E702": 22, "E731": 1, "B905": 4, "B023": 32}`。包含B023/B905等潜在逻辑规则，不全是格式。旧R410仅四文件的40项基线不能代表本次全范围；本轮未引入源码改动。
- Ruff format：139文件需格式化，原输出 `139 files would be reformatted, 706 files already formatted`；Prettier 11文件。
- 中文CLI：342条MISSING标记；pytest另暴露40个公共文档字符串缺口及2330个tracked路径覆盖缺口，三者计量口径不同。
- 文档规则：18条，`{"sensitive_content": 6, "script_reference_exists": 11, "markdown_link_exists": 1}`。规则命中未经逐项裁定为实际敏感值泄露或真实引用损坏；原详细扫描保留本地，精选审计只保存脱敏分类。
- Mypy：实际命令为 `python -m mypy --cache-dir <fresh> -p cloud_edge_robot_arm`，exit2，提示缺少py.typed；仓库CI入口是 `python -m mypy .`。本次没有形成有效源码类型检查结果，也没有追加改入口重跑；不能把exit2解释为源码类型错误数量。
- API导出：原OpenAPI与生成JSON解析后也不等价，TS生成文件同样不同。差异包括PublicationStatusView、AttemptView/SimulationRunRecord等publication字段、BatchProgress.confirmed_succeeded/unconfirmed_terminal、BatchRecord.publication_state和TimelineEvent.historical_payload。生成、typegen、Prettier三个原步骤均在新输出目录完成，原仓库生成文件未被覆盖。

前端单测43PASS，app/node类型检查、ESLint、构建PASS；这些通过不替代生成契约一致性检查。详见[静态与前端审计](static-frontend-audit.json)。

浏览器默认39PASS+1原有SKIP、research 3PASS；合计42PASS+1SKIP。旧19项按classname+name逐项比较，19项全部PASS，额外skip=0；原有E2E06因PLAYWRIGHT_MUJOCO_RUNTIME=0保留，缺失duration保持null。两suite使用新DB、workers=1、retries=0、reuseExistingServer=false，断言及原等待不放宽；结束后默认8000/5173与research8123/5199端口可用、owned子树回收。MuJoCo/EGL图像仿真不等同实体机器人。

研究页面观测：scope=SOFTWARE_ONLY、groups=600、assigned=4200、blocked=4200、actual_research_status=NOT_RUN、formal_accepted=false，导出与页面一致。这是展示/导出契约，不是4200项真实研究成功。[浏览器逐项核验](browser-audit.json)。

## 5. Phase12 full矩阵与真实性审计

预期20个实验、5580登记结果行；实有manifest=5580、raw=5580、unique run_id=5580。矩阵计量以scenario×backend×mode×seed×repetition展开；F20的policy task_count=100不能据180行就宣称完成18000个实际任务。

| 实验 | 预期行 | 实有行 | raw状态 | raw调用/完成声明 |
| --- | --- | --- | --- | --- |
| F01_PC_SC_BASELINE | 180 | 180 | {"SUCCESS": 180} | 180 / 180 |
| F02_ETEAC_BASELINE | 180 | 180 | {"SUCCESS": 180} | 180 / 180 |
| F03_AUTO_BASELINE | 180 | 180 | {"SUCCESS": 180} | 180 / 180 |
| F04_NETWORK_LATENCY | 360 | 360 | {"SUCCESS": 360} | 360 / 360 |
| F05_NETWORK_JITTER | 180 | 180 | {"SUCCESS": 180} | 180 / 180 |
| F06_PACKET_LOSS | 360 | 360 | {"SUCCESS": 360} | 360 / 360 |
| F07_CLOUD_INTERRUPTION | 180 | 180 | {"SUCCESS": 180} | 180 / 180 |
| F08_TARGET_MOVEMENT | 360 | 360 | {"SUCCESS": 360} | 360 / 360 |
| F09_OBSTACLE_CHANGE | 360 | 360 | {"SUCCESS": 360} | 360 / 360 |
| F10_LOCAL_RECOVERY | 120 | 120 | {"SUCCESS": 120} | 120 / 120 |
| F11_LOCAL_REPLANNING | 360 | 360 | {"SUCCESS": 180, "FAILED": 180} | 360 / 360 |
| F12_SAFETY_REJECTION | 720 | 720 | {"SAFETY_STOPPED": 360, "BLOCKED_BY_ENV": 360} | 360 / 360 |
| F13_SKILL_CACHE | 240 | 240 | {"SUCCESS": 240} | 240 / 240 |
| F14_AUTO_POLICY | 180 | 180 | {"SUCCESS": 180} | 180 / 180 |
| F15_MUJOCO_ISAAC_PAIRED | 360 | 360 | {"SUCCESS": 120, "BLOCKED_BY_ENV": 180, "SAFETY_STOPPED": 60} | 180 / 180 |
| F16_PLANNER_PROVIDER_COMPARISON | 360 | 360 | {"SUCCESS": 180, "BLOCKED_BY_ENV": 180} | 180 / 180 |
| F17_ABLATION_RECOVERY | 120 | 120 | {"SUCCESS": 120} | 120 / 120 |
| F18_ABLATION_REPLANNING | 240 | 240 | {"SUCCESS": 120, "FAILED": 120} | 240 / 240 |
| F19_ABLATION_SAFETY | 360 | 360 | {"FAILED": 180, "SAFETY_STOPPED": 180} | 360 / 360 |
| F20_STRESS_AND_RECOVERY | 180 | 180 | {"SUCCESS": 180} | 180 / 180 |

raw声明：adapter尝试5580、runtime调用4860、runtime完成4860、environment阻塞720、阻塞前未调用runtime 720、synthetic pipeline样本0、raw-declared authoritative=4860。这些是原始字段聚合，不能直接解释成有效完成任务或正式权威样本。

独立检查Phase11内层main/duplicate/recovery回执后，不支持外层完成声明的行数900；其中F20为180，支持F20声明的回执仅0。内层状态与外层SUCCESS矛盾保持，不修改raw或用清单代替native证据。

最终verifier原值：status=`PHASE12_REJECTED`；thesis_status=`THESIS_PACKAGE_INCOMPLETE`；full_profile_execution_status=`REJECTED`；project_status=`NOT_CLOSED`；verifier-gated authoritative rows=`0`。退出码0的run/analyze/export只说明相应程序结束，不能替代verifier或真实研究验收。

verifier未通过的检查：

- `duplicate_competition_evidence_exists`
- `paired_backend_acceptance_status_correct`
- `recovery_evidence_valid`
- `runner_invocation_count_exactly_one`

离线结构/计数/内层回执审计事项：

- `PHASE11_TOP_LEVEL_CLAIM_UNSUPPORTED_BY_INNER_RECEIPT`：{'count': 900, 'by_experiment': {'F04_NETWORK_LATENCY': 180, 'F05_NETWORK_JITTER': 180, 'F06_PACKET_LOSS': 360, 'F20_STRESS_AND_RECOVERY': 180}}
- `F20_TOP_LEVEL_CLAIM_UNSUPPORTED_BY_INNER_RECEIPT`：{'count': 180}

ISAAC_SIM_ROOT与ROS_DISTRO未注入子环境，外部planner adapter固定BLOCKED_BY_ENV；verify的skip flags只是输出字段，不是run阶段安全门禁。本轮不触发外部模型/实体硬件。环境前置NVIDIA字段含driver错误文本，预探测在受限上下文运行，不能把非空文本或本轮EGL通过升级为全主机GPU/Isaac已验收。各字段与原始文件SHA见[phase12-audit.json](phase12-audit.json)。

## 6. 两次前置交接、来源与资源边界

R414实际Astra计划在原073未启动时追加launched=false、attempts=0管理guard。原parent自然在Popen前拒绝，session12273实际exit1，属于预期管理交接；同7节点新scope只移除SIMULATION_RUNTIME_DB覆盖，完整7PASS、15.548432秒。6份实际DB分别位于各test/artifacts，未产生stage共享DB；旧字节不改。

R415实际Astra先静态定位原尾部mkdir缺少parents问题。原075随后正常耗尽1800秒额度，source一致、SIGTERM后root/child回收；交接没有主动发送信号。旧parent在首个tail的r223/resources准备处实际FileNotFoundError，尚未invoked该tail；原partial目录保留。原076管理guard未启动也未触发拒绝。新runner复用原run_one/bounded_stage，派生execute仅修资源子目录parents/exist_ok与tail namespace，AST反向归一化和compile核验；只接续38个从未STARTED节点并继续剩余队列。原075失败/未完成与两处零行为管理slot不重复计数。[R414步骤](../../round414-workbench-db-scope-preflight-handoff-20261103/handoff-step-report.md)、[R415步骤](../../round415-unstarted-tail-resource-parent-handoff-20261103/handoff-step-report.md)。

最终全部1309份运行来源pin相等，tracked开发源码diff为空，Git HEAD仍为被测ab18；main与两处gitlink的外层index SHA未变，未进入dirty gitlink目录。经批准主机/proc核验已观察owned身份1934个，最终存活0；Python前置记录418份均accepted。官方real_robot源指纹、NUL规范化清单hash、Phase12 provenance源hash采用不同算法，不能因digest不同就断言同源冲突。详见[最终来源/清理](../postflight/checks.json)。

资源采样实际为每20秒读取owned进程CPU ticks/RSS；计划中周期cgroup采样没有实现，这是观测范围偏差。没有据此断言OOM、生产资源峰值或旧R407退出原因；旧R407精确exit仍UNKNOWN。原生回执保留的patched_worktree=true/旧字段名属于继承标签，以当前实际HEAD与pin核对来源，不改写原件使其好看。

完整raw、运行DB/WAL/SHM、外置/tmp、fixtures重复副本、images/traces、缓存、凭据、模型和SDK不进入精选Git包。交付manifest记录选择与边界，不能冒充完整远端复现包。全部开发验证、真实软件/仿真调用、正式研究/实体硬件验收分开；本轮formal_accepted=false。Git交付与fresh whole-evidence review在本轮delivery/review下独立记录，不以失败消失作为报告交付条件。
