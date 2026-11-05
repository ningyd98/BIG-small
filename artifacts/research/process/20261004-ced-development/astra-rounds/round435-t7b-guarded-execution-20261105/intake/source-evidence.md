# R435 original source evidence

Read-only intake; no test/model/render/physical execution. Line numbers refer to pinned HEAD source bytes.

## src/cloud_edge_robot_arm/simulation/mujoco/backend.py:165

```text
165: def _observed_operation(kind: str):
166:     def decorate(function):
167:         @wraps(function)
168:         def observed(self, *args, **kwargs):
169:             if self._operation_observer is None:
170:                 return function(self, *args, **kwargs)
171:             self._require_not_in_observer_callback()
172:             requested = args[0] if args else next(iter(kwargs.values()), None)
173:             parameters: dict[str, Any] = {}
174:             if kind == "COMMAND":
175:                 names = {
176:                     "apply_joint_targets": "joint_target",
177:                     "apply_gripper_command": "gripper",
178:                     "hold_current_joints": "hold_current_joints",
179:                     "_emergency_stop_observed": "emergency_stop",
180:                 }
181:                 parameters["command_type"] = names[function.__name__]
182:             if requested is not None:
183:                 parameters["requested"] = requested
184:             with self._operation_source(kind, parameters) as source:
185:                 result = function(self, *args, **kwargs)
186:                 source["returned"] = result
187:                 return result
188: 
189:         return observed
190: 
191:     return decorate
```

## src/cloud_edge_robot_arm/simulation/mujoco/backend.py:280

```text
280:     def _operation_result(self, kind: str, returned: Any, command_start: int) -> dict[str, Any]:
281:         if kind == "CONTROL":
282:             return {"control_state": self._build_actuator_observation()}
283:         if kind == "CAPTURE":
284:             frame, ids, labels, hashes = returned
285:             return {
286:                 "sensor_frame": frame,
287:                 "instance_ids": ids,
288:                 "instance_labels": {str(key): value for key, value in labels.items()},
289:                 "pass_state_hashes": hashes,
290:             }
291:         result: dict[str, Any] = {"physics_state": self.current_physics_observation()}
292:         if kind == "RESET":
293:             assert self._config is not None and self._data is not None
294:             result.update(
295:                 initial_controller_targets={
296:                     "joints_rad": tuple(float(value) for value in self._target_positions),
297:                     "fingers_m": tuple(float(value) for value in self._data.ctrl[7:9]),
298:                 },
299:                 physics_dt_s=self._config.physics_dt_s,
300:                 actuator_delay_steps=self._actuator_delay_steps,
301:             )
302:         if kind == "COMMAND":
303:             result["command_records"] = self.command_records[command_start:]
```

## src/cloud_edge_robot_arm/simulation/mujoco/backend.py:306

```text
306:     def _emit_operation_source(
307:         self,
308:         operation_id: int,
309:         kind: str,
310:         phase: str,
311:         parameters: Mapping[str, Any],
312:         result: Any,
313:         error: BaseException | None,
314:     ) -> None:
315:         callback = self._operation_observer
316:         row = {
317:             "operation_id": operation_id,
318:             "kind": kind,
319:             "phase": phase,
320:             "episode_id": self._episode_id,
321:             "physics_step": self._total_physics_steps,
322:             "error_type": None if error is None else type(error).__name__,
323:             "error": None if error is None else _operation_error_text(error),
324:         }
325:         self._operation_ledger.append(_operation_detach(row))
326:         started = monotonic_ns()
327:         try:
328:             event = BackendOperationBoundary(
329:                 operation_id,
330:                 kind,
331:                 phase,
332:                 self._episode_id,
333:                 self._total_physics_steps,
334:                 self.get_sim_time() if self._data is not None else None,
335:                 parameters,
336:                 result,
337:                 row["error_type"],
338:                 row["error"],
339:             )
340:             self._in_observer_callback = True
341:             if callback is not None:
342:                 callback(event)
343:         except BaseException as observer_error:
344:             self._operation_observer_failures.append(
345:                 _operation_detach(
346:                     {
347:                         **row,
348:                         "observer_error_type": type(observer_error).__name__,
349:                         "observer_error": _operation_error_text(observer_error),
350:                     }
351:                 )
352:             )
353:         finally:
354:             self._in_observer_callback = False
355:             self._operation_observer_overhead_ns += monotonic_ns() - started
356: 
357:     @contextmanager
358:     def _operation_source(
359:         self, kind: str, parameters: Mapping[str, Any]
360:     ) -> Iterator[dict[str, Any]]:
361:         self._operation_sequence += 1
362:         number = self._operation_sequence
363:         command_start = len(self._command_records)
364:         source: dict[str, Any] = {}
365:         parameters = dict(parameters)
366:         if kind == "CAPTURE":
367:             try:
368:                 parameters["camera_state"] = self._operation_camera_state()
369:                 parameters["physics_state"] = self.current_physics_observation()
370:             except BaseException as source_error:
371:                 self._operation_observer_failures.append(
372:                     _operation_detach(
373:                         {
374:                             "operation_id": number,
375:                             "kind": kind,
376:                             "phase": "BEGIN",
377:                             "observer_error_type": type(source_error).__name__,
378:                             "observer_error": _operation_error_text(source_error),
379:                         }
380:                     )
381:                 )
382:         self._emit_operation_source(number, kind, "BEGIN", parameters, None, None)
383:         error: BaseException | None = None
384:         try:
385:             yield source
386:         except BaseException as operation_error:
387:             error = operation_error
388:             raise
389:         finally:
390:             result = None
391:             try:
392:                 if error is None:
393:                     result = self._operation_result(kind, source.get("returned"), command_start)
394:                 elif kind == "COMMAND":
395:                     result = {"command_records": self.command_records[command_start:]}
396:             except BaseException as source_error:
397:                 self._operation_observer_failures.append(
398:                     _operation_detach(
399:                         {
400:                             "operation_id": number,
401:                             "kind": kind,
402:                             "phase": "END",
403:                             "observer_error_type": type(source_error).__name__,
404:                             "observer_error": _operation_error_text(source_error),
405:                         }
406:                     )
407:                 )
408:             self._emit_operation_source(number, kind, "END", parameters, result, error)
```

## src/cloud_edge_robot_arm/simulation/mujoco/backend.py:554

```text
554:     def step(self, steps: int = 1) -> SimulationStepResult:
555:         self._require_not_in_observer_callback()
556:         self._require_loaded()
557:         assert self._mujoco is not None and self._model is not None and self._data is not None
558:         if steps < 1:
559:             raise ValueError("steps must be positive")
560:         observer = self._step_observer
561:         executed = 0
562:         if self._operation_observer is not None:
563:             for _ in range(steps):
564:                 self._apply_control()
565:                 self._emit_actuator_observation()
566:                 self._advance_observed_physics_step()
567:                 executed += 1
568:                 if observer is not None:
569:                     snapshot = self._build_physics_observation(self._last_contacts)
570:                     self._in_observer_callback = True
571:                     try:
572:                         observer(snapshot)
573:                     except BaseException:
574:                         self._step_observer = None
575:                         raise
576:                     finally:
577:                         self._in_observer_callback = False
578:         elif observer is None:
579:             for _ in range(steps):
580:                 # Emergency stop blocks new commands but actively holds joints.
581:                 self._apply_control()
582:                 self._emit_actuator_observation()
583:                 self._mujoco.mj_step(self._model, self._data)
584:                 executed += 1
585:                 self._total_physics_steps += 1
586:             self._last_contacts = self._read_contacts()
587:         else:
588:             for _ in range(steps):
589:                 self._apply_control()
590:                 self._emit_actuator_observation()
591:                 self._mujoco.mj_step(self._model, self._data)
592:                 executed += 1
593:                 self._total_physics_steps += 1
594:                 self._last_contacts = self._read_contacts()
595:                 snapshot = self._build_physics_observation(self._last_contacts)
596:                 self._in_observer_callback = True
597:                 try:
598:                     observer(snapshot)
599:                 except BaseException:
600:                     self._step_observer = None
601:                     raise
602:                 finally:
603:                     self._in_observer_callback = False
604:         self._update_sensor_frame()
605:         return SimulationStepResult(
606:             sim_time_s=self.get_sim_time(),
607:             physics_steps=executed,
608:             contacts=list(self._last_contacts),
609:             sensor_frame=self._sensor_frame,
610:         )
611: 
612:     @_observed_operation("PHYSICS")
613:     def _advance_observed_physics_step(self) -> None:
614:         assert self._mujoco is not None and self._model is not None and self._data is not None
615:         self._mujoco.mj_step(self._model, self._data)
616:         self._total_physics_steps += 1
617:         self._last_contacts = self._read_contacts()
```

## src/cloud_edge_robot_arm/simulation/mujoco/backend.py:765

```text
765:     def apply_joint_targets(self, targets: JointCommand) -> None:
766:         self._require_not_in_observer_callback()
767:         if self._estop_engaged:
768:             self._record_command(
769:                 "joint_target",
770:                 accepted=False,
771:                 reason="emergency_stop",
772:                 target_positions_rad=list(targets.positions),
773:             )
774:             return
775:         if len(targets.positions) != 7:
776:             raise ValueError("Franka Panda profile requires exactly 7 joint targets")
777:         clipped = np.clip(np.array(targets.positions, dtype=float), -2.8, 2.8)
778:         if self._actuator_delay_steps:
779:             available_step = self._total_physics_steps + self._actuator_delay_steps
780:             self._pending_joint_targets.append((available_step, clipped))
781:             self._record_command(
782:                 "joint_target",
783:                 accepted=True,
784:                 reason=f"queued_until_physics_step={available_step}",
785:                 target_positions_rad=list(targets.positions),
786:                 applied_target_positions_rad=clipped.tolist(),
787:             )
788:         else:
789:             self._target_positions = clipped
790:             self._record_command(
791:                 "joint_target",
792:                 accepted=True,
793:                 reason="",
794:                 target_positions_rad=list(targets.positions),
795:                 applied_target_positions_rad=clipped.tolist(),
796:             )
797: 
798:     @_observed_operation("COMMAND")
799:     def apply_gripper_command(self, command: GripperCommand) -> None:
800:         self._require_not_in_observer_callback()
801:         if self._estop_engaged:
802:             self._record_command(
803:                 "gripper", accepted=False, reason="emergency_stop", target_open=command.open
804:             )
805:             return
806:         self._gripper_open = command.open
807:         assert self._data is not None
808:         target = GRIPPER_OPEN_TARGET_M if command.open else 0.0
809:         if self._data.ctrl.shape[0] >= 9:
810:             self._data.ctrl[7] = target
811:             self._data.ctrl[8] = target
812:         self._record_command("gripper", accepted=True, reason="", target_open=command.open)
813: 
814:     def emergency_stop(self) -> None:
815:         self._require_not_in_observer_callback()
816:         self.hold_current_joints()
817:         if self._operation_observer is not None:
818:             self._emergency_stop_observed()
819:             return
820:         self._estop_engaged = True
821:         self._record_command("emergency_stop", accepted=True, reason="")
822:         self._apply_control()
823: 
824:     @_observed_operation("COMMAND")
825:     def _emergency_stop_observed(self) -> None:
826:         self._estop_engaged = True
827:         self._record_command("emergency_stop", accepted=True, reason="")
828:         self._apply_control()
829: 
830:     @_observed_operation("COMMAND")
831:     def hold_current_joints(self) -> None:
832:         """Cancel queued arm motion and actively hold measured joints."""
833:         self._require_not_in_observer_callback()
834:         self._require_loaded()
835:         assert self._data is not None
836:         self._pending_joint_targets.clear()
837:         self._target_positions = np.array(self._data.qpos[:7], dtype=float)
838:         self._record_command(
839:             "hold_current_joints",
840:             accepted=True,
841:             reason="motion_terminated",
842:             target_positions_rad=self._target_positions.tolist(),
843:             applied_target_positions_rad=self._target_positions.tolist(),
844:         )
```

## src/cloud_edge_robot_arm/simulation/mujoco/backend.py:975

```text
975:     def _apply_control(self) -> None:
976:         assert self._data is not None and self._model is not None
977:         self._apply_target_motion()
978:         while (
979:             self._pending_joint_targets
980:             and self._pending_joint_targets[0][0] <= self._total_physics_steps
981:         ):
982:             _, self._target_positions = self._pending_joint_targets.pop(0)
983:         current = np.array(self._data.qpos[:7], dtype=float)
984:         error = self._target_positions - current
985:         control = current + np.clip(error, -0.10, 0.10)
986:         # Position actuators still drive every arm movement. Their command is
987:         # offset by the measured generalized gravity/Coriolis load so a slow
988:         # trajectory does not let this reference arm fold under its own weight.
989:         gains = self._model.actuator_gainprm[:7, 0]
990:         feedforward = self._data.qfrc_bias[:7] / gains
991:         self._data.ctrl[:7] = np.clip(
992:             control + feedforward,
993:             self._model.actuator_ctrlrange[:7, 0],
994:             self._model.actuator_ctrlrange[:7, 1],
995:         )
996: 
```

## src/cloud_edge_robot_arm/research/operational_prefix_v1.py:303

```text
303:             "input_mode": "RGBD",
304:             "execution_scope": "VISION_CLOSED_LOOP",
305:             "backend": "MUJOCO",
306:             "scenarios": ["S01_NORMAL_STATIC"],
307:             "control_modes": ["PCSC"],
308:             "seeds": [0],
309:             "user_instruction": "excluded operational RESET120 capture prefix; no actions",
310:         }
311:         job = record.repository.create_job(
312:             run_id="operational-prefix-" + uuid4().hex,
313:             batch_id="",
314:             backend="MUJOCO",
315:             scenario_id="S01_NORMAL_STATIC",
316:             control_mode="PCSC",
317:             seed=0,
318:             manifest_id="simulation.operational-prefix.v1",
319:             reproducibility_hash=hashlib.sha256(canonical_bytes_v1(assignment)).hexdigest(),
320:             draft=assignment,
321:             timeout_seconds=60,
322:             max_attempts=1,
323:             artifact_root="worker-attempt",
324:             source_commit="SOURCE_ONLY_CURRENT_BYTES",
325:             source_tree_hash=hashlib.sha256(
326:                 canonical_bytes_v1(inputs["source_inventory"])
327:             ).hexdigest(),
328:             provenance={
329:                 "scope": "EXCLUDED_SOURCE_ONLY_PREFIX",
330:                 "config_sha256": inputs["config_sha256"],
331:             },
332:         )
333:         record.job_id = job.job_id
334:         record.assignment_json = canonical_bytes_v1(_assignment_basis(job))
335:         queued = record.repository.update_status_cas(
336:             job.job_id,
337:             expected=RuntimeJobStatus.CREATED,
338:             next_status=RuntimeJobStatus.QUEUED,
339:             reason_code="operational_prefix_startup",
340:             worker_id="",
```

## src/cloud_edge_robot_arm/research/operational_prefix_v1.py:1430

```text
1430:             _failure_row_v1(record, "failure_archival", archive_error, primary_id=primary_id)
1431:             _persist_failure_stage_v1(record, record.output, primary_id=primary_id)
1432: 
1433:     try:
1434:         source = _prepare_source_v1(application, worker, job, start_monotonic=start_monotonic)
1435:         source.backend.initialize(source.capture._config)
1436:         _check_source_v1(application)
1437:         resources.enter_context(source.capture)
1438:         record.issuing = True
1439:         try:
1440:             recorder = OperationalPrefixRecorderV1.from_application(
1441:                 application,
1442:                 source.backend,
1443:                 source.capture,
1444:                 source.executor,
1445:                 directory=source.directory,
1446:             )
1447:         finally:
1448:             record.issuing = False
1449:         resources.enter_context(recorder)
1450:         application.check_recorder(recorder)
1451:         source.backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
1452:         application.check_recorder(recorder)
1453:         with recorder.purpose("SETTLE"):
1454:             source.backend.step(steps=120)
1455:         application.check_recorder(recorder)
1456:         recorder.capture()
1457:         application.check_recorder(recorder)
1458:         recorder.read_capture_current()
1459:         application.check_recorder(recorder)
1460:         if (
1461:             source.backend.operation_observer_failures
1462:             or recorder._d_failures
1463:             or recorder._audit_failures
1464:         ):
1465:             raise RuntimeError("retained backend/D/super observer failure")
1466:         _write_exclusive_v1(source.directory / "prefix-failures.json", canonical_bytes_v1([]))
1467:         recorder.freeze_operational_prefix()
1468:         receipt = _publish_operational_prefix_v1(application, recorder)
1469:     except BaseException as error:
1470:         preserve(error, "runner")
1471:     finally:
1472:         try:
```

## src/cloud_edge_robot_arm/research/operational_time_v1.py:342

```text
342:         self._check()
343:         record = self._event_record(after)
344:         if record.mark_point is None:
345:             raise OperationalTimeError("current requires a prior event MARK")
346:         lower = self._read()
347:         current_point = self._point()
348:         upper = self._read()
349:         receipt = OperationalBracket(self._domain, uuid.uuid4().hex, lower, upper)
350:         self._receipts[id(receipt)] = _ReceiptRecord(receipt, after, "current", current_point)
351:         self._check()
352:         return receipt
353: 
354:     def age_bounds(self, event: OperationalBracket, current: OperationalBracket) -> OperationalAge:
355:         self._check()
```

## src/cloud_edge_robot_arm/research/operational_time_v1.py:385

```text
385:     def start_deadline(
386:         self, *, task_key: str, origin: OperationalBracket, budget_ns: int
387:     ) -> OperationalDeadline:
388:         self._check()
389:         _text(task_key, "task_key")
390:         _integer(budget_ns, "budget_ns", positive=True)
391:         origin_record = self._receipt_record(origin)
392:         token_record = self._event_record(origin_record.token)
393:         if origin_record.role != "event" or token_record.receipt is not origin:
394:             raise OperationalTimeError("deadline origin requires a complete event receipt")
395:         existing = self._deadlines.get(task_key)
396:         if existing is not None:
397:             if existing.origin is not origin or existing.budget_ns != budget_ns:
398:                 raise OperationalTimeError("original task deadline cannot be refreshed")
399:             self._check()
400:             return existing
401:         deadline = OperationalDeadline(
402:             self._domain,
403:             origin,
404:             task_key,
405:             budget_ns,
406:             origin.lower_ns + budget_ns,
407:             uuid.uuid4().hex,
408:         )
409:         self._deadlines[task_key] = deadline
410:         self._deadline_handles[id(deadline)] = deadline
411:         self._check()
412:         return deadline
413: 
414:     def before_deadline(self, deadline: OperationalDeadline, current: OperationalBracket) -> bool:
415:         self._check()
416:         if (
417:             type(deadline) is not OperationalDeadline
418:             or self._deadline_handles.get(id(deadline)) is not deadline
419:             or deadline.domain is not self._domain
420:             or self._deadlines.get(deadline.task_key) is not deadline
421:         ):
422:             raise OperationalTimeError("deadline is foreign or unissued")
423:         self.age_bounds(deadline.origin, current)
424:         return current.upper_ns < deadline.deadline_ns
```

## src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py:90

```text
90: )
91: _BOUNDARY_SLIM = set("operation_id kind phase episode_id physics_step error_type error".split())
92: _QUALIFICATION = ("same_session_private_producer_unavailable", "execution_deadline_guards_unproven")
```

## src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py:118

```text
118:     allocated_acquisition_count: int
119:     recorded_physics_count: int
120:     original_failures: tuple[str, ...]
121:     structural_reasons: tuple[str, ...]
122:     coverage_status: str
123:     schema_version: str = field(default="native.completion.full-horizon-audit.v1", init=False)
124:     qualification_reasons: tuple[str, ...] = field(default=_QUALIFICATION, init=False)
125:     producer_status: str = field(default="UNAVAILABLE", init=False)
126:     guard_status: str = field(default="NOT_PROVEN", init=False)
127:     evidence_scope: str = field(default="SOFTWARE_ONLY", init=False)
128:     native_authority: str = field(default="UNAVAILABLE", init=False)
129:     qualification: str = field(default="UNKNOWN", init=False)
130: 
```

## artifacts/research/process/20261004-ced-development/astra-rounds/round91-native-full-action-support-20261007/design.md:64

```text
64: 
65: 一个真实 owner 的 PRE/POST physics-operation hook 在现有 backend observer 汇流处覆盖**每一步**（包括 chunk、render、wait），不可注册第二物理推进者/第二 recorder。D deadline precheck 证明当时许可，postcheck 发现晚返回时保留真实已发生 effect，并禁止成功/后续步。不声称 precheck 消除了任意阻塞间隙、不声称在硬期限前必然完成；正常链验收须真实未过期地到达完整终态。TTL 在原要求的观测消费/提交/后置验证处检查，不能自造“每步都用旧帧重做 native”要求，也不能删现有要求的消费点。
66: 
67: collector 的逐物理步 RGB-D 记录保留 max gap .005S、每个分配帧和完整终态。离线收集可以用独立 development wall 预算，不冒充 native/Tcap。在线沿同一物理控制、完整 H 和噪声/相机域；记录层是否每步保存 raw 要显式登记。任何声称记录层不改变物理作用的适配须 CPU 验证它不 step、不改 actuator/qpos、不引入新控制决策；D 成本差异全部实测且不用于推出 H_D。
68: 
69: ## 5. 生产与重建的接口（均为 PROPOSED）
70: 
71: - `vision/native_completion.py` 新增 frozen `NativeCompletionReferenceV2`：schema、recipe_id/hash、skill、object/region、observation_id/hash、compiled_payload/hash、original_owner/checkpoint/binding IDs、policy/geometry/source generation、control_points、reference_kind、full_horizon_steps、physics_dt、capture_step、episode、support_domain_digest。不含 truth，public 构造仅描述。
72: - 同文件 `resolve_completion_reference_v2(online, contract, step, *, resolved, grounding, role_binding, owner) -> NativeCompletionReferenceV2`；GRASP 从真实本体姿态、RELEASE 从 exact PLACE binding 派生。`NativeCompletionTimingV2` 保存真实 capture/dispatch/terminal event IDs与step、完整分项、D窗口ID、timing_requirement；factory决定 mode，public flag无权限。
73: - `simulation/mujoco/native_horizon.py` 新增内部 `NativeHorizonSession.from_owner(owner, *, reference, timing)`，`before_operation(kind, step)` / `after_operation(kind, step)` / `finish_action(result) -> ActionResult`。只调现有 robot/backend hold/step，从不另解 IK/选动作/写pose；由现有执行入口和受限 collector 接入，private active capability 校验当前唯一 owner。result保留原controller结果，另记actual steps/hold/effect/expiry，不覆盖原失败。
74: - `research/native_completion_calibration.py` 新增 `reconstruct_completion_group(registration, group) -> CompletionGroupDiagnostics`、`reconstruct_completion_registry(registration) -> CompletionCalibrationDiagnostics`，读取真实原件与 OC1/P5/P6 lineage。先严格原件校验，再全帧 decoder 与离线真值分离，重算 owner、p/r/x/G/U/L/M/C、全H和组连接图；不信任缓存summary/q/PASS。
75: - `research/native_completion_calibration.py` 同时定义 `NativeOperationalGroupEnvelopeV2` 与 `read_native_operational_group(registration, group)`：新生产的真实OC1事件/预注册/RESET/owner/完整S分项与原RGB-D、physics、action库存逐一绑定；复用RawV3结构/哈希/物理一致性检查，单独输出旧UTC仍UNKNOWN和新operational source判定。不得把旧reader的UTC缺口整体忽略成COMPLETE、不能将旧原件改scope标签或retrofit为新域。新sidecar由同次真实producer生成，引用每份原件原始SHA与事件身份；未匹配一个必需项即本组件infinity。
76: - 新 `NativeCompletionRegistrationV2` 字段：schema=`native.calibration.operational.v2`、recipe/metric版本、scope、preregistration OC1事件链、完整 assigned_groups、independence ancestry、sources、scene/camera/marker/noise/asset/controller/grounder pins、八技能 horizon分项/support、age_S=0、timing mode、coverage=.9、max_sample_gap=.005、全部raw inventory。旧UTC registry reader保持严格，不用scope字符串变更给旧raw换域。
```
