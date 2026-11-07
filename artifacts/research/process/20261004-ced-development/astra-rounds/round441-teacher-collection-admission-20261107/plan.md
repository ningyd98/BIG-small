# R441 有限教师采集准入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 沿R439 superpowers:executing-plans inline；只修改R439已允许的新模块/新测试/新配置，不改旧tracker、条件评估器、worker条件表或Shield。

**Goal:** 解除“先有校准才能收集校准原件”的实验准入循环，保留每条原条件及UNKNOWN，绝不将实验授权当作在线PASS/native权限。

**Architecture:** TEACHER_COLLECTION工厂在原条件评估之后另作私有实验准入决定，只对固定技能/阶段/明确校准缺口允许继续。在线条件结果仍原样保存；共享grounder/controller/Shield和全部来源/时效/硬停约束不变；独立reader分开报告完整采集、实验条件缺口、数值诊断和物理结果。

**Tech Stack:** 当前OpenCV/MuJoCo/Python；此规划只读源码与写本目录元数据。

**Spec:** R91 design.md第4/5节明确有限development teacher、TEACHER_COLLECTION与native隔离；R439及R440；R91缺项/UNKNOWN→infinity规则保持。

## 静态原始问题

1. `tracking.py:622–626`：depth_error_bound_m=None使target_reachable及其后视觉效果事实value=None，原因calibrated_depth_error_bound_missing。当前marker_association.py将该界保留None；没有本轮可用独立认证深度界，不能填0或任意有限数。
2. `_physical_stability_unknown`无论端点窗口如何都保留None，原因inter_frame_motion_not_bounded、quarter_turn_symmetry_unresolved。禁止把端点一致性改成连续稳定证明。
3. worker_owner._PRE要求MOVE_ABOVE/APPROACH/GRASP的target_reachable；_POST LIFT要求object_held/object_lifted/object_stable。tracker._CONDITIONS不包含object_held，所以评估器还会返回visual_fact_missing_or_untrusted_source。此静态缺口纳入同一轮，不要运行后再把它当计划外新发现。
4. conditions._visual_verdict将有合法身份/深度的None事实统一变为visual_fact_not_boolean，丢失底层原因。因此必须同时保存原fact和ConditionVerdict，不能仅白名单这个通用verdict字符串。
5. R439写“允许缺校准数值资格”又要求这些canonical全PASS，使首动作不可达。修正的是本轮实验准入语义；旧线上全条件门原样严格。

完整原始行片段/输入SHA在intake文件，不将静态问题说成实际试验失败。T1/T2 RED及T1 GREEN已发生额度不重置。

## 许可边界与精确白名单

新的返回值只能为 `COLLECTION_STEP_ALLOWED` 或 `COLLECTION_STOP`，不是ConditionStatus、EvidenceVerdict、VALID、PASS或native授权。工厂能力必须来自本轮exact live应用、当前0001 assignment、同source generation与限定八动作序列。public scope/字符串/传入bool/伪造verdict均不能签发或延长能力。

下表仅允许**原值仍UNKNOWN**且全部共同门成立时继续固定实验；任何FAIL均停。每项都精确匹配技能、阶段、condition名、真实源fact、原verdict理由；不能按字符串后缀/通配/所有视觉条件放行。

|阶段/技能|条件|允许的底层缺口和附加要求|
|---|---|---|
|PRE：MOVE_ABOVE、APPROACH、GRASP|target_reachable|fact.value=None、fact.reasons恰calibrated_depth_error_bound_missing、实际tracker.depth_error_bound_m is None；measured_values.stationary_support必须True。若False，即使外层UNKNOWN仍停。|
|POST：LIFT|object_lifted、object_stable|fact.value=None且理由恰calibrated_depth_error_bound_missing；原本体gripper_holding和tcp_at_resolved_target均PASS、controller成功且注册完整H/hold记录完整。|
|POST：LIFT|object_stable|或底层理由集合恰{inter_frame_motion_not_bounded,quarter_turn_symmetry_unresolved}，真实tracker自己产出，不注入depth界；连续原始记录完整但不称连续视觉证书。|
|POST：LIFT|object_held|仅当前已pin的OpenCVTargetTracker生产接口本就不提供此key，保存完整未经改写的facts映射；ConditionVerdict理由恰visual_fact_missing_or_untrusted_source，或holding_feedback_required组合时再含robot_state_condition_satisfied；独立gripper_holding必须PASS。任何已提供后丢失/改写的fact、未知tracker实现或其他原因均停。|
|PRE：RELEASE|object_inside_target_region|fact.value=None且理由恰calibrated_depth_error_bound_missing；必须有同assignment此前PLACE完整成功receipt、当前holding PASS与当前完整对象/区域像素几何。附加下述实验位置核对，不宣称已证明inside。|
|POST：RETREAT（最后动作，不再启动动作）及TERMINAL|object_inside_target_region、placement_stable|底层恰calibrated_depth_error_bound_missing；placement_stable也可为上述两项连续运动/旋转缺口。只允许完整结束“采集”，最终视觉效果仍UNKNOWN。|
|POST：RETREAT及TERMINAL|object_placed|原evaluate_conditions递归的object_inside_target_region为上述唯一允许缺深度界UNKNOWN，gripper_released必须PASS；组合UNKNOWN原样保留，原reasons只允许visual_fact_not_boolean与robot_state_condition_satisfied这两个递归结果，不允许其他缺口。|

除object_placed递归组合外，所有有fact的上表项还要求原ConditionVerdict恰UNKNOWN/visual_fact_not_boolean，fact的source/observation/hash/episode/identity/pixel与当前实际frame吻合；组合condition的本体分支不得FAIL/UNKNOWN。对象颜色/标记/完整轮廓证据缺失不属于白名单。object_held是明确唯一的结构性缺项例外，不允许把其他visual_fact_missing_or_untrusted_source泛化放行。

本collector固定TaskContract.completion_criteria为 `object_placed` 与 `placement_stable`，直接复用compile_worker_original_plan的canonical _PRE/_POST及最后RETREAT带入的两个完整criteria，不能为了运行清空或改写它们。上述RETREAT/TERMINAL两行只允许结束实验，不授权继续物理动作。其他别名、原skill_*_completed等不在此固定骨架准入白名单；若意外引入，不删条件，停并记录。TERMINAL原本体gripper_released/robot_in_safe_pose仍必须PASS。

## 共同硬门（全部成立才有实验许可）

- 当前私有应用/lease/原deadline/cancel/boot/thread/source身份有效；原TTL5s、capture=dispatch S步及所有原接收/消费点不变。观测stale、future、身份/来源/校准版本不符一律停。
- 每次真实图像可解码、深度有效；marker身份与注册一致，当前完整对象与目标区几何可读，target_visible PASS，非裁切/部分遮挡/身份跳变/无效深度。这里“几何可读”只是现算法实际返回的完整像素支持，不等于已校准误差界；禁止在None时注入0或用truth填几何。
- required RobotState真实、connected、无estop/碰撞；原本体条件全部PASS；GRASP/LIFT/搬运/PLACE所需双侧接触和holding保持按既有controller，本体持物丢失即停。既有Shield pre/post/所有hard-limits照常；拒绝/限参需要重编译按原规则，不能忽略。
- 无任何原条件FAIL；原动作controller failure、partial、超H/欠H/缺tail、guard/source/observer错误即停。允许的post UNKNOWN只影响是否可执行下一段固定实验，不把原动作语义成功改成PASS。
- RELEASE额外要求当前原始对象完整可见xy测量包络落在同帧区域可读内边界，当前表面高度差按既有`.012m`名义检查、原PLACE exact payload/receipt与当前TCP通过原tolerance；不得添加测量误差0证书。这是有限实验的可观测位置核对，结果字段须标 `nominal_collection_position_check`，原object_inside_target_region仍UNKNOWN。名义检查失败/读不出就停。不得使用离线physics真值决定是否释放。
- 原注册每步采样/尾部与所有分配帧完整；missing/UNKNOWN像素重建不按本白名单掩盖。离线truth只落raw/独立评价，不参与上述门或动作选择。

## 具体接口与修改

仅R439已有新文件：

- `research/native_collection_application.py`：私有 `_evaluate_collection_admission` 接收当前应用绑定的phase/step、**内部实际调用**evaluate_conditions的原verdict、同一次tracker原facts、真实robot/原Shield结果及绑定receipt。不可接受调用方作为权威的预计算PASS/q。返回不可变 `CollectionAdmissionDecision`（phase、step_id、allowed、retained_unknown_conditions、reason、原frame/condition/fact/Shield/source digest）；其构造本身不授权，只有live工厂消费一次。原条件列表/hash不得变化。
- `native_calibration_collection.py`/配置：固定白名单版本 `teacher.collection.admission.v1`与精确表格、必须门、source pins写入prepare protocol；计划/data schema标明实验许可，不能注册为线上condition支持。控制序列仍R439八动作，不生成分支恢复或重试。
- `native_full_horizon_recorder.py`：原ConditionSpec/ConditionVerdict/facts（包含None、全部reasons）、原robot/Shield、白名单行ID、每次准入前后当前来源与时间、CONTINUE_EXPERIMENT/STOP决定及receipt全存，不能覆盖/清洗。原动作结果、complete_horizon和semantic_effect_status分字段。
- `native_full_horizon_originals.py`：重新读取原条件/facts/版本，重算白名单及共同门和独立physical。即使collector写allowed=True，reader不信此值；不在白名单/共同门缺证据则组无效。truth始终只在reader/独立物理评分。
- 新测试仅并入R439已计划的test_native_collection_authority/collection/grounding及full_horizon_originals文件；不新建产品路径，不改旧条件评估器/tracker/worker_owner/Shield。

## 数据与结论分层（避免另一种循环）

本轮有限实验可以在上述明确UNKNOWN下收集完整原件，结束状态最多 `COLLECTION_COMPLETE_WITH_UNRESOLVED_EFFECTS`；`online_effect_status=UNKNOWN`、`native_qualification=UNKNOWN`、`execution_admitted=false`（线上意义）与`teacher_collection_admitted=true`分开。

R91未知/缺项分母规则**不由本修订取消**：若required canonical effect仍UNKNOWN，则原group qualification score仍infinity（JSON None）。reader可以另报原始重算的G/U/L/M/C数值诊断和physical_success True/False，但不得把这一诊断代入qualified reduction或把UNKNOWN动作变COMPLETE。仅source/horizon完整也不构成有限q。这一首组的价值是获得独立原件、暴露真实感知/效果/资源缺口，不是预先保证校准资格。

因此本计划解除的是**实验执行**死锁；要让此类组将来成为合格独立校准来源，仍需独立验证的深度/完整区间效果支持或有明确研究设计依据的资格协议，由后续实际Astra基于首组原件制定，不能从本试验自身先宣称VALID。本轮不扩大这部分产品范围；九组批量继续关闭。若没有任何帧能满足共同硬门，实际入口应失败并保留证据，不把它宣传为“完整动作已执行”。

## 测试与运行承接

- [ ] 在尚未执行的R439 T2 GREEN内增加CPU用例：首三技能只有真实缺深度界UNKNOWN可进入实验而verdict不变；白名单错skill/phase/condition/reason拒绝；target_reachable.stationary_support=False拒绝；无效深度/遮挡/旧帧/身份错误/任何FAIL拒绝；fake/copy capability拒绝；原条件hash未变。
- [ ] LIFT结构性object_held缺项单独验证：只有pin的原tracker缺key+holding PASS允许；删除其他key/任意missing fact/holding FAIL拒绝；object_stable通用effect_evidence_incomplete不允许。RELEASE无PLACE receipt、名义几何不在区域/缺几何全部拒绝。truth getter设抛错sentinel仍不影响合法实验判断。
- [ ] T3 GREEN内增加独立bytes反例：allowed缓存篡改、UNKNOWN改PASS、白名单换reason、原条件删项、source hash替换、terminal物理成功被改成native成功均拒绝；完整实验+物理成功但required UNKNOWN时qualified score仍None，保留有限diagnostic metric且不进入九组认证。
- [ ] 不新增RED/测试阶段或额度，不重跑已耗T1/T2 RED。继续R439/R440原t2-green、t3-red/green、最终限定回归/static/唯一review；R440真实节点deselect保持。原唯一0001实际、12960步、时间/内存/磁盘预算不变；无模型调用、无试跑、无额外初始化。

## 规划执行与自审

本代理只读和写本目录，产品编辑/测试/physics/render=0。输入SHA与静态原片段在intake。自审已覆盖通用visual_fact_not_boolean被误用、object_held未实现事实、stationary_support=False被深度None掩盖、终态UNKNOWN/physical_success混同与有限分数伪资格；均有明确拒绝/保留规则。R439中“所有必要条件必须PASS”的教师解释由本限定白名单覆盖，线上原规则不变。
