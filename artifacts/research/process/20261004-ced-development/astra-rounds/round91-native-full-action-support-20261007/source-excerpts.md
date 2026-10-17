# R91 bounded original excerpts
Exact lines from pinned local inputs; quotations are evidence, not newly executed results.
P2 failure is frozen unsupported-source/reconstruction evidence, not a new test run. No raw experiment payload copied.

## docs/superpowers/specs/2026-10-03-rgbd-evidence-research-design.md:78-86
```text
78: 确定性安全门先排除不可行动作；在其余动作中以预测失败损失、实测推理/网络成本与切换成本选择动作。使用启发式优化或有限候选期望成本比较的首个实现，必须与现有人工加权规则比较，不宣称全局最优。运行中在技能安全边界、证据失效、异常到达及云端返回后重新决策；原子动作期间禁止非安全原因强制切换，硬停止独立。
79: 
80: ### 4.3 证据有效期与局部修复
81: 
82: 契约记录 observation_id、calibration_version、目标位置误差界、采集时刻、动作预计持续时间、传感器需求、前后置条件及版本。候选充分条件为：校准后的几何误差界加目标运动上界乘以“观测年龄与预计动作持续时间之和”，不超过该动作允许误差。不能估计运动界、目标身份不确定、深度失效或标定不匹配时判为 UNKNOWN，转入重观测或停止；不能把未知当作安全。
83: 
84: 云端返回与提交动作前都复核，版本与几何上下文必须一致。几何前置条件失效后定位最早受影响步骤，只替换有依赖的未完成后缀；已完成物理效果用新观测确认，完成步骤不可重放；补丁包含依赖和版本约束，不允许越过 SafetyShield。经验零碰撞不构成无条件安全证明。
85: 
86: ### 4.4 有限候选判断与决策生命周期
```

## docs/superpowers/specs/2026-10-03-rgbd-mujoco-dataset-design.md:18-25
```text
18: 
19: - 在线模型输入必须包含 RGB 与注册深度；禁止无提示降级为文字或 Mock。
20: - 深度语义为 optical_z_m：光轴方向距离、米、little-endian float32；0 表示无效。
21: - 相机坐标为 +X 向右、+Y 向下、+Z 向前；camera_to_world 为行优先 4×4 刚体变换。
22: - 默认采集分辨率 320×240，数据集配置可选择 640×480；最大宽高 1280×720。
23: - 在线观测在接收时超过 5000 ms 或超前服务器超过 1000 ms 即拒绝；离线数据通过专用读取器处理，不修改历史时间戳伪装实时数据。
24: - 默认本地模型 qwen3-vl:4b-instruct，默认服务 http://127.0.0.1:11434；不承诺未经实测的速度与精度。
25: - 初始每个 GPU 只运行一个渲染进程，批内复用模型和渲染器。
```

## docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md:103-115
```text
103: |---|---|
104: | G0 | 已发生感知/模型/动作阶段100%真实；泄露、伪装成功、跨组重复0；不可用BLOCKED，未发生NOT_EXECUTED |
105: | G1 | 正确识别且有效深度目标定位P90≤10mm，另报覆盖；独立静态抓放成功≥90% |
106: | G2 / C1 | 对B0云请求均值减少≥30%；成功率差单侧95%下界>−3百分点；安全违规率差单侧95%上界≤+1百分点 |
107: | G2a | 应用字节减少≥25%；失败惩罚任务耗时P95减少≥15%，分别判定 |
108: | G3 / C2 | 对B3误放行减少≥50%、绝对≤2%；有效安全机会错误拒绝≤5%，UNKNOWN独立 |
109: | G4 / C2 | 200故障恢复成功≥80%；失败惩罚恢复耗时中位数减少≥30%；完成的不可重复动作重提交0 |
110: | G5 可选 | 2000训练组域外成功提高≥5百分点；500/1000/2000曲线，300域外组×3训练seed |
111: 
112: 基线selection的静态≥90%、整体≥80%、安全违规≤1%不变。没有合格B0时报告NO_FEASIBLE_BASELINE，不能用低成功率宣称请求节省。正式G0/G1通过后才验收C1/C2；软件通过和开发smoke不替代正式结果。
113: 
114: G1定位误差对独立标注的物体顶部几何中心计算三维欧氏距离，不能以选中像素处的真值反投影自比较。相对改进的基线值为0时记N/A并另报绝对值；名义改进阈值按点估计判定，可靠改善还要求对应95%区间排除0，不把点估计达标写成置信下界达到同一阈值。
115: 
```

## docs/superpowers/plans/2026-10-05-operational-clock-repair-supplement.md:7-18
```text
7: ## 必须先冻结的合同
8: 
9: - D是冻结平台的真实操作计数域；S是同backend/episode的仿真时间/physics step。请求端到端、TTL、PCSC周期、任务/恢复wall预算使用D；0.005秒采样gap、物理抬升/保持/放置稳定使用S。记录实际 `(D_BEGIN,D_END,S_BEGIN,S_END,kind,step,owner)`，不得把S秒当D秒。
10: - 真实事件与当前检查点的同域括号分别为 `[c−,c+]`、`[n−,n+]`；在原始因果关系成立后，年龄上界为 `(n+−c−)/10^9`。未知来源、跨域、倒退、未来/逆序先拒绝，不用midpoint或clamp隐藏。普通/condition五秒、接收5000ms和未来1000ms规则不放宽。
11: - 原任务起点括号 `[b−,b+]` 和固定预算T产生保守截止 `b−+T×10^9`。deadline等值拒绝；重观测、晚回复、新event、重启或重试不刷新截止。真正事务及dispatch前重新读当前D。所有rounding向拒绝方向。
12: - 实际startup authority绑定计数API/实现、boot/epoch、app、worker、capture和原lease/fencing；caller字符串、PID、readonly/hash或resolution不是授权或SI精度。时钟选择须有实际平台语义证据，完整wall预算必须含suspend；缺此支持不验收。
13: - 单机操作计数域不保证SI/UTC精度、跨机时间或真实机器人安全。真实非空外部UTC期限、第三方lease/证书/JWT及远端图像仍走原严格路由；没有域间桥接证据则不支持新域。
14: - 历史年龄和当前比较不能生成未来执行界。sim timeout不得充当完整未来 `H_D`；经验平均/割线不得充当运动上界。几何/完整动作source和至少九个独立支持组、coverage .9、10mm及全部统计门保持。强制完整future窗口而缺对应支持时，新域也必须UNKNOWN。
15: 
16: ## 四项有序任务
17: 
18: - [ ] **OC1：新域类型、reader与边界数学。** 新增独立的operational-domain/bracket/deadline类型及最小reader，不复用datetime冒充UTC。来源仅由实际startup工厂签发；记录时间实现与suspend/重启scope。先取得真实接口的CPU RED→GREEN：5秒/5秒+1ns、deadline等值、缺pair、foreign domain/copied handle/boot漂移、合法重叠、UTC跳变仅诊断、未来/乱序及原deadline不刷新。此步仅SOFTWARE，不给应用native源授权。
```

## artifacts/research/process/20261004-ced-development/astra-repair-planning/clock-dependency-review.md:62-73
```text
62: 同时保留S：实际backend/episode中的仿真时间/physics step。0.005s最大采样gap、50mm/.5s保持和1s放置稳定均沿原simulation物理定义；不改成host计时。TTL、云请求端到端、PCSC .5/1/2/5周期、任务/恢复wall预算用D。记录每段完整 `(D_BEGIN,D_END,S_BEGIN,S_END,kind,step,owner)`，区分WAIT、controller、renderer和无物理推进时段。
63: 
64: 已有 `ExperimentClock` 只把请求等待的D时长转换成要推进的sim步；其mapping不是所有主动动作全局S=D的证明。CPU阻塞、render成本和catch-up形成实际piecewise轨迹。不能从已观测局部平均斜率/割线推断未来S/D上界；不能把sim m/s乘D年龄，或把D m/s乘sim horizon。
65: 
66: 原充分条件须在一个物理运动支持域中重新一致表达，例如：
67: 
68: - 若校准给出 `v_S`（米/模拟秒），使用同backend真实capture与current S的保守差 `age_S`，并用认证的完整 `H_S`：`E + v_S*(age_S+H_S) <= 0.01m`；另独立执行原5秒D TTL和所有D deadlines。未来等待/排队的sim推进必须包含在实际登记horizon范围内，不能只算controller步数。
69: - 若使用 `v_D`，须有原独立校准对同一D、同一调度/仿真策略的实际支持，并且 `H_D` 来自可支撑的完整动作合同；过去采样割线不能充当上界。更改时钟类型/映射/调度适用域后不能复用旧v_D证书。
70: - 当前native全horizon endpoint经验误差量与运动supremum不同。可保留精确owner/参考/完整S horizon的原经验终态定义，但不能标成连续速度或未来稳定性；coverage .9与所有缺组分母仍适用。
71: 
72: **保守历史年龄不自动给未来耗时界。** `now_plus+H_D<=deadline_D`只有在H_D确是对应完整执行的支持界时，才是整个未来窗口的充分检查；max(timeout_ms,expected_duration_ms)目前还被controller解释成sim步预算，不能直接用作H_D。若只有计划/经验预计时长，必须标该条件假设，并依既有deadline在每个允许的真实effect边界重新检查；不能宣称硬期限内完成已获证明。若现有native准入合同强制完整未来D窗口，而没有对应支持H_D，则新域也必须UNKNOWN，此审计不建议改低该门。独立UTC同样不能凭授时本身补出H_D。
73: 
```

## docs/superpowers/plans/2026-10-05-astra-repair-plan.md:99-107
```text
99: **Files:** 扩展 `S/vision/native_calibration.py`、`S/research/native_geometry_calibration.py`、`tests/test_native_calibration_source.py`，新增 `tests/test_native_calibration_v2.py`、`scripts/collect_native_calibration_v2.py`、`configs/research/native_calibration_v2.json`；index/catalog/registry及所有原件写R04的新版本目录，应用index路径固定 `configs/research/native_calibration_sources.json`，沿现有factory入口增加显式v2。v1原件/报告不改。
100: 
101: **Interfaces:** 延续 `NativeCalibrationSource.from_application(role_binding: RoleRuntimeBinding) -> NativeCalibrationSource` 和 `.revalidate(role_binding)`；新增显式v2 schema分支消费R3 owned catalog、签名预注册与独立UTC sidecar，原RawV3 `utc_uncertainty_ns=None`仍如实保留。新CLI `--config PATH --output PATH --group-id ID --execute-once`由真实应用factory采一个已预分配组，不能调用DIRECT_OFFLINE_SCENE_ADAPTER冒充RESET。
102: 
103: - [ ] 先RED测试v1仍缺RESET而INCOMPLETE、public登记/局部数值/mock verifier不能构造source；v2修改后的原pair/source/owner/horizon/compiled-model/asset/TCP/contact/ref/policy必须全部重算。运行 `.venv/bin/python -m pytest -q tests/test_native_calibration_source.py tests/test_native_calibration_v2.py`，最小实现后GREEN及静态。
104: - [ ] 预注册完整来源组库存、固定reference/recipe/full horizons、范围和独立性图，不将R1或prefix改名充组。开发资产/640×480/实际noise与默认域差异需明确作用域；不能用零噪声离线场景证明默认0.001m native噪声支持。
105: - [ ] 首先执行一个新预注册完整组（待实现CLI）：`MUJOCO_GL=egl .venv/bin/python scripts/collect_native_calibration_v2.py --config configs/research/native_calibration_v2.json --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R04/group-001 --group-id group-001 --execute-once`。验证实际owned图与全部原件可重放；一组只证明source链，不声称n=9统计有限。
106: - [ ] 首组链路及clock期限可行后，按预登记顺序逐组采集至少9个独立且支持的组，所有分配/失败组件进分母。`ceil((9+1)*.9)=9`，9组有一个UNKNOWN即不能给finite；更多组只能按预登记有界规则，不能删除失败/重命名共享component或为显著性不断追加。
107: - [ ] 从完整顶点/接触/TCP/原resolved owner全horizon独立重建geometry/action经验界及范围，构造真实 `from_application` 正分支；finite或准入失败均报告。端点误差不能冒充连续supremum/未来稳定性，短窗口不能借完整horizon终态界。独审原件/分组/source链后root单独提交producer/registry，消费者仍待R5。
```

## src/cloud_edge_robot_arm/research/native_geometry_calibration.py:352-390
```text
352: def reconstruct_truth_endpoint(
353:     scope: NativeGeometryRegistration,
354:     policy: DeterministicGroundingPolicy,
355:     skill: str,
356:     original_physics: Mapping[str, Any],
357: ) -> tuple[float, float, float] | None:
358:     """Offline endpoint arithmetic using the exact already reconstructed owner policy."""
359:     geometry = scope.to_payload()
360:     center = _vector(list(original_physics["object_geom_position_m"]), 3)
361:     rotation = _vector(list(original_physics["object_geom_rotation_row_major"]), 9).reshape(3, 3)
362:     grasp = center + rotation @ _rigid(geometry["object_to_tcp"])[:3, 3]
363:     current = _vector(list(original_physics["tcp_position_m"]), 3)
364:     if skill in {"LIFT", "RETREAT"}:
365:         target = (
366:             current[0],
367:             current[1],
368:             max(current[2] + policy.clearance_m, policy.minimum_height_m),
369:         )
370:     elif skill in {"MOVE_TO_REGION", "PLACE"}:
371:         region = geometry["region_world_m"]
372:         z = (
373:             max(policy.minimum_height_m, grasp[2] + policy.clearance_m)
374:             if skill == "MOVE_TO_REGION"
375:             else region[2] + grasp[2] - geometry["support_height_m"]
376:         )
377:         target = (region[0], region[1], z)
378:     elif skill in {"MOVE_ABOVE", "APPROACH"}:
379:         target = (
380:             grasp[0],
381:             grasp[1],
382:             max(policy.minimum_height_m, grasp[2] + policy.clearance_m)
383:             if skill == "MOVE_ABOVE"
384:             else grasp[2],
385:         )
386:     else:
387:         return None
388:     return (float(target[0]), float(target[1]), float(target[2]))
389: 
390: 
```

## src/cloud_edge_robot_arm/research/native_geometry_calibration.py:640-680
```text
640:             ):
641:                 raise ValueError("original action owner receipt differs from source reconstruction")
642:             duration = rebound.expected_duration_s
643:             if (
644:                 duration != horizon
645:                 or duration
646:                 < max(rebound.grounded_step.timeout_ms, rebound.grounded_step.expected_duration_ms)
647:                 / 1000
648:             ):
649:                 unavailable = True
650:                 continue
651:             # Whole nominal horizon must be present; never shorten to observed success duration.
652:             start_time = interval.start_sim_time_s
653:             end_time = start_time + horizon
654:             terminal = [
655:                 s for s in raw.values() if math.isclose(s["sim_time_s"], end_time, abs_tol=1e-8)
656:             ]
657:             if len(terminal) != 1 or any(
658:                 i.kind == "EXECUTOR_ATTEMPT"
659:                 and i.interval_id != interval.interval_id
660:                 and start_time < i.start_sim_time_s < end_time
661:                 for i in records.intervals
662:             ):
663:                 unavailable = True
664:                 continue
665:             target = rebound.grounded_step.parameters.get("target_pose")
666:             if target is None:
667:                 unavailable = True
668:                 continue
669:             policy = DeterministicGroundingPolicy(**owner["grounding_policy"])
670:             true_goal = reconstruct_truth_endpoint(scope, policy, skill, state)
671:             if true_goal is None:
672:                 unavailable = True
673:                 continue
674:             # Joint completion quantity already includes localization + actual terminal tracking.
675:             goal_error = float(np.linalg.norm(np.array([target[k] for k in "xyz"]) - true_goal))
676:             terminal_error = float(
677:                 np.linalg.norm(np.array(terminal[0]["tcp_position_m"]) - true_goal)
678:             )
679:             values.append(max(geo, goal_error, terminal_error))
680:         action_errors[skill] = max(values) if values and not unavailable else None
```

## src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py:150-181
```text
150:             tcp_velocity=tcp_velocity, acceleration=acceleration,
151:             details={"requested_height_m": height_m},
152:         )
153:         if not action.success:
154:             return action
155:         config = self._backend._config
156:         assert config is not None
157:         requested_hold_steps = math.ceil(0.5 / config.physics_dt_s)
158:         held_steps = 0
159:         bilateral_held = True
160:         while held_steps < requested_hold_steps:
161:             chunk = min(5, requested_hold_steps - held_steps)
162:             self._backend.step(steps=chunk)
163:             held_steps += chunk
164:             contacts = self._grasp_contacts()
165:             if contacts["left"] == 0 or contacts["right"] == 0:
166:                 bilateral_held = False
167:                 break
168:         tcp_lift_m = self._backend.get_tcp_pose().z - current.z
169:         success = bilateral_held and held_steps >= requested_hold_steps and tcp_lift_m >= 0.05
170:         error = None if success else (
171:             "GRASP_LOST" if not bilateral_held else "LIFT_SHORTFALL"
172:         )
173:         return self._result(
174:             "LIFT", success, action.state_before, action.started_at,
175:             int(action.details["physics_steps"]) + held_steps, error,
176:             details={
177:                 **{key: value for key, value in action.details.items() if key != "physics_steps"},
178:                 "measured_tcp_lift_m": tcp_lift_m,
179:                 "contact_hold_s": held_steps * config.physics_dt_s,
180:                 "completion_evidence": "TCP_LIFT_AND_BILATERAL_CONTACT_ONLY",
181:             },
```

