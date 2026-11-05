# R435 fresh Astra 独立代码审查

实际审查者：gpt-6-astra，独立任务 `astra_r435_fresh_review`。审查基线 `9ce1972fa8bd9858fb48c15145b5b82d5a4bf953`；最终输入为 R436 两处验证契约修正后的四文件，SHA256 见同名 JSON。此审查只读，未运行测试、MuJoCo、模型或子代理。原 R435/R436 验证结果没有被当作本审查的新执行结果。

## Strengths

- COMMAND/CONTROL 的检查置于 BEGIN observer 之后；三条 physics 分支都经真实 mj_step 前后检查。postcheck 前累加实际步数，能保留已经发生的物理效果。
- 原始 OC1 deadline、owner、backend/episode 绑定，不接受 caller now；正常退出和拒绝后的 backend 生命周期封闭，callback 重入入口具有独立检查。
- 不可打印异常保护、detached guard events 和 stop secondary 记录提供了保留主因的基础。诊断明确维持 UNKNOWN/UNAVAILABLE，未伪装完整 H 或 native 权限。

## Issues

### Critical

无。

### Important

#### R435-F1 [P1] Safety-stop bypass admits foreign-thread commands before estop is engaged

- 位置：`src/cloud_edge_robot_arm/simulation/mujoco/backend.py:352`（关联范围 352–363）。
- 原始静态证据：_check_execution_guard returns for every non-PHYSICS kind whenever _guard_stop_depth is nonzero, before closed and thread checks. emergency_stop increments this shared depth before hold_current_joints and sets estop only afterwards.
- 可复现路径（尚未执行）：Thread A enters safety stop after guard rejection; pause its hold_current_joints before return. Thread B calls apply_gripper_command(open=False). Its COMMAND BEFORE/AFTER and RETURN checks all bypass, estop is still false, and ctrl[7:9] changes with an accepted gripper record. Resume A: joint HOLD does not undo that gripper effect. A Thread/Event software fixture can make this schedule deterministic.
- 实际影响：An already rejected/closed guarded session accepts a new actuator command from the wrong thread during its stop path.
- 限定修复：Restrict bypass to the exact internal synchronous CONTROL call of the active stopping thread; reject ordinary COMMAND, step/PHYSICS and unrelated RETURN checks before any effect. Preserve permitted STOP/HOLD and avoid making safety stop depend on the failing ordinary guard.

#### R435-F2 [P1] An operation observer failure alone does not close the guarded session

- 位置：`src/cloud_edge_robot_arm/simulation/mujoco/backend.py:499`（关联范围 499–517）。
- 原始静态证据：_emit_operation_source catches BaseException and only appends _operation_observer_failures; _check_execution_guard does not consume that failure and normal observer return is indistinguishable from failure to the decorated effect.
- 可复现路径（尚未执行）：Install a guard which permits every boundary and an operation observer which raises a sentinel exception on COMMAND BEGIN. apply_joint_targets changes the target and returns successfully; step(2) can advance two steps. Repeat for CONTROL/PHYSICS BEGIN and END: none closes the active session solely because the observer failed.
- 实际影响：Missing or failed source recording does not stop guarded execution, contrary to R435 Review Focus 3 and diagnostic fail-stop requirements. The existing test combines an observer failure with a guard rejection, so it does not test this independent cause.
- 限定修复：For active guarded sessions, retain the first original observer/source failure and fail closed at the pre-effect or post-observer checkpoint, outside callback reentry state. Preserve existing unguarded passive-observer semantics and ensure observer failures during STOP cannot block STOP or replace an earlier primary.

#### R435-F3 [P2] Diagnostic PASS ignores guard-retained stop and snapshot failures

- 位置：`src/cloud_edge_robot_arm/research/guarded_execution_v1.py:278`（关联范围 278–315）。
- 原始静态证据：Expected expired COMMAND catches TimeoutError at lines 244-249. _close_execution_guard preserves a stop failure as stop_error_type/stop_error in execution_guard_events and a snapshot failure as snapshot_error. The diagnostic serializes these events but computes status only from local primary/secondary, without merging retained failures.
- 可复现路径（尚未执行）：Make the first safety-stop CONTROL call fail after estop is set; retain the original deadline TimeoutError. Let the explicit later STOP succeed. The expected refusal list and two-step count remain correct, operation_observer_failures may remain empty, and status becomes PASS even though guard-events contains the unexpected stop failure. The snapshot_error variant is similarly omitted.
- 实际影响：The result claims diagnostic success despite a recorded unexpected safety-stop/snapshot failure; the separate secondary_errors summary is incomplete.
- 限定修复：Add a pure diagnostic failure-merge helper and feed it actual retained guard-event failures before status is calculated. Preserve the expected deadline refusal as expected, but mark any retained stop/snapshot failure FAIL and include typed/staged secondary details. Unit-test with genuine software-backend-generated guard events; no extra actual diagnostic is needed.

### Minor

无。

## Review Focus coverage

1. effect 前重新检查：三条 physics 路径及 COMMAND/CONTROL BEGIN 后位置正确；F1 是停止 bypass 的额外入口。
2. post/END/legacy 后到期：有对应 post/RETURN 或下一 CONTROL precheck；已发生步数在 post 前累加，不再推进下一步。
3. 失效不可复活：deadline、owner identity、cancel 和常规 operation 异常路径封闭；独立 operation-observer 失败遗漏为 F2。
4. STOP/HOLD 和主异常：普通 guard failure 由 closure 保留主因，stop failure 保存 secondary；F1/F3 分别指出绕过边界和诊断归并缺陷。
5. callback 重入：公开 step/COMMAND/reset/STOP/initialize/shutdown/observer 注册前均检查 callback 标志；不把反射私有字段当隔离承诺。

## Declined to judge

- Complete full-H producer, worker/lease/hard-stop ownership and native three-consumer admission: explicitly outside R435; UNKNOWN/UNAVAILABLE/NOT_PROVEN must remain.
- Hard preemption of a blocking mj_step or elimination of the final Python instruction gap after a check: explicitly not promised; this review checks pre/post behavior and retained completed effects.
- Malicious in-process reflection or replacement of private backend/guard fields: explicitly outside the isolation contract. The thread-bypass finding uses ordinary public commands, not reflection.
- Actual MuJoCo/BOOTTIME success, environment readiness, final runner execution and formal research acceptance: no actual diagnostic has run at review time and reviewer was prohibited from running tests or physics. Parent must supply fresh evidence.
- Known R435 RuntimeError-vs-TimeoutError test failures and four historical mypy narrowings: handled by actual-Astra R436; not counted again as new findings. R436 focused 2 PASS is parent-reported, not independently rerun.
- Application-level completeness of the future raw package, native calibration and physical grasp/lift outcomes: not outputs of the fixed two-step diagnostic.

## Assessment

**Ready to merge: No.** 三项 Important 进入唯一修复 pass；软件与实际诊断通过前不可宣称完成。R437 应新增确定性反例、一次 RED→GREEN，并执行尚未消耗的真实诊断；不再派第二审查代理。
