# R91: native.action_completion.operational.v2 设计合同（待 ROOT 接受）

这是 P2 之后的新版本设计，actual=0，software implementation=0，formal=0。P2 原合同与 NOT_SUPPORTED 结论保持原样。本文不把经验界改名为确定性安全保证。

## 1. 时域要求的出处与量词

绑定 `2026-10-03-rgbd-evidence-research-design.md:82` 将 `E+v*(age+预计持续时间)`称为“候选充分条件”，同时明确不能估计运动界则 UNKNOWN。旧 schema 的这个分支继续如此，不给 v 填 0。

原 Astra `clock-dependency-review.md:67–72` 则明确：

- `v_S` 分支用同 backend 的 `age_S` 和认证完整 `H_S`，**另独立执行原 5 秒 D TTL 和所有 D deadlines**。
- `v_D` 分支须有对应 D/调度域的校准与完整 `H_D`；过去斜率不构成上界。
- 原完整 horizon endpoint **经验终态**量可以保留，但不能标成连续速度或未来稳定性。
- “若现有native准入合同强制完整未来D窗口，而没有对应支持H_D，则新域也必须UNKNOWN”。这是条件句，不是每个 S 域动作必须提供 H_D 的全称要求。

`2026-10-05-operational-clock-repair-supplement.md:16` 重申同一条件。原 R4 计划明确允许完整终态经验误差、coverage .9 和全部缺组分母。`ced.research.v2` 的 G1 仍是定位 P90≤10mm、独立静态抓放≥90%，并非任意 host pause 下的硬实时完成定理。

**结论：**可以新增工厂签发的 `timing_requirement=CHECKPOINT_D_FULL_S` 路由。其 `future_wall_bound_ns=None` 的状态是 `NOT_REQUIRED_FOR_THIS_RECIPE`，不是 0 或已证明；仍有完整真实 H_S 及原 D 守卫。旧 UTC、外部时钟和显式 `FULL_FUTURE_D_REQUIRED` 路由原样拒绝缺 H_D。路由来自注册配方和真实 owner，不接受调用者选择较弱标志；不改变旧 P2 数据的 UNKNOWN。

接收“超前服务器 1000ms”来自继承 dataset spec:23，是外部观测时间规则，不是执行未来 H_D。外部 UTC 路由不搬成 D；本地 OC1 因果事件反序直接拒绝，不能借这 1000ms。普通/condition 5 秒和接收 5000ms 保持等值允许、+1ns拒绝；deadline 等值拒绝。任何未来 wall 时长假设仅诊断，不进入认证。

## 2. 版本化的量：显式替代充分条件，不修改旧 e/v

新增配方 `FULL_HORIZON_JOINT_CONTACT_COMPLETION_V2`，域为单 owner、单 MuJoCo backend/episode、固定 dt、已登记资产/相机/可见标记/噪声/控制器/grounder、无外部动力学写入。目标不是证明连续速度，而是对规定完整 S 终态误差进行原规则的独立组校准。

对一次动作，在真实 capture c、真正 dispatch s、规定完整终态 t=s+H 定义：

- `G`：原完整刚体顶点、接触杠杆、TCP 几何重建误差，保留原定义和所有已分配帧。
- `p`：实际编译并经 Shield 检查的命令参考；GRASP 是同一 capture 的实际本体 TCP 保持参考。它来自像素/本体/注册常量，不能读取对象真值。
- `r(c), r(t)`：**仅离线**从原物理状态和注册 object_to_tcp/grounding policy 重建的正确接触参考。
- `U=||p-r(c)||`：定位、命令参考误差。
- `L=||x(t)-p||`：真实终态跟踪/保持误差。
- `M=||r(t)-r(c)||`：该完整窗口内的终态参考漂移；单独保存，不能叫速度，不能放入旧 geometric_error_bound_m。
- `C=max(G, U+L+M)`。三角不等式给 `||x(t)-r(t)||<=U+L+M`。有独立连续 v 时才可另推 `M<=v*(age_S+H_S)`；反方向不成立。本方案不从有限采样推出连续 v。

实际接触点/完整物体量为多个登记控制点时，对每点计算同式后取最大；旋转必须通过刚体变换作用于接触点/八顶点，不能只比较中心。需要保持的原条件在其真实保持区间每物理步重建并计入最大分数；其余动作只宣称完整 nominal horizon 的终态预测，不能把启动时本就远离目标的 TCP 距离当必须≤10mm，也不能宣称全路径无碰撞。

这是一项**明确的新联合经验充分条件**：同原 group recipe 对 C 校准后 `q_joint<=0.01m` 才能给该新路径数值资格。`geometric_error_bound_m` 和 `motion_bound_m_s` 旧字段不被填成 C/0；新 verdict 带 `bound_kind=JOINT_COMPLETION_V2`、`joint_completion_bound_m`、分量/配方 digest。缺来源、缺原组或出域仍 UNKNOWN。ROOT 接受的是这个公开的新配方；未接受时只实施独立 CPU 工作，不启用在线准入。若要求所有路径仍必须提供连续 v 而不允许原 R4 已接受的联合经验终态量，则本配方不可启用，须明确改变该工程配方要求或提供真正的连续运动证书，不能偷偷过旧门。

coverage .9 沿既有 group 方法：先每独立组件内对所有必需动作/帧/终态取联合最大，再 `k=ceil((n+1)*.9)`，n=9 时取最大。任何必需项缺失、未执行、动作失败、UNKNOWN、部分原件使该组件为 infinity。不得把八个各 .9 的独立门当整链 .9，不能声称无条件分布保证；声明同注册域、组隔离和可交换性条件。C 可能比旧终态量更保守，真实 q 不一定≤10mm；失败就保留失败。

## 3. 动作闭包和正常链

|技能|新配方参考/量|独立后置条件|
|---|---|---|
|MOVE_ABOVE|原 grounder 对对象接触点加 clearance，离线 r(c)/r(t)均按同公式重建，C 明示目标漂移|在线完整目标可见、原高度/姿态条件、Shield|
|APPROACH|object_to_tcp 正确接触变换；同 C|真实接近条件，不以动作返回代替|
|GRASP|保持的实际 TCP 是 p，对象正确接触 TCP 是 r；动作无 target_pose 也可重建，不能虚造零向量 target_pose|原双侧接触、本体与新 RGB-D holding 证据各自记录，真值不进入在线|
|LIFT/RETREAT|经来源/payload核对的固定命令端点；reference drift M=0仅此固定参考，U/L/G 仍全校准|物体真实抬升≥50mm和≥.5S保持由独立物理评价；TCP抬升不替代|
|MOVE_TO_REGION/PLACE|精确 resolved 固定区域端点，同 U/L/G；整物体/接触姿态误差仍有贡献|放置、持物等原条件|
|RELEASE（明确新增）|来自已执行 PLACE 的 exact payload 与已登记刚体 grasp transform，重建目标物体放置变换；x/r/p 对应八顶点而非只看 TCP；开启后的接触解除/落稳误差进入同一 C|新帧整物体在目标区域、已释放，独立真实落稳≥1S；不能把 gripper_open 当成功|

RELEASE 新定义是为了完成正常抓放链，不能沿 P2 未支持状态直接放行。没有匹配的 PLACE receipt/完整刚体变换则 UNKNOWN，不根据可见几个像素造 placement frame。HOME 仍按既有可选省略规则，非本轮 native 支持。OBSERVE/VERIFY 等非物理技能不伪造动作校准，沿原观测/验证路径。

v2 初始年龄支持精确限定 `capture_step==dispatch_step`；渲染/解码耗时计 D，期间 S 必须被冻结且 source-owned。云请求期间若 S 推进，返回后真实重观测并重建同版本 exact payload/Shield，再检查原 deadline；不可改 cached 时间或延长任务预算。这样初始正常域不借未知 age_S 漂移；未来扩展非零年龄必须另登记量和数据。动作内 S 只能由唯一受控 step 推进；并行 catch-up/其他动作拒绝或在已经登记的完整 horizon 内逐段记账，不能漏掉。D 时钟自由流逝不意味着 S 自行运动，只是这个仿真域的性质，绝不泛化到硬件。

## 4. 完整 horizon 的真正生产

旧 controller 提前成功后 teacher 立即下一动作，会污染 nominal 终态；现 GRASP 没有 endpoint；LIFT `_move` 后再做 ceil(.5/dt) 步。因此必须生产完整窗口，而非只改 estimator。

新增注册的 horizon 配方，以整数步派生：`N=ceil(max(original timeout, original expected, compiled timeout, compiled expected, effective owner required duration)/dt)`，再纳入**尚未包含**的技能内置附加步骤（LIFT .5S hold、RELEASE 1S稳定观察）及登记等待。通过带分项的 `HorizonBreakdown` 防重复加和或少加。实际 H=N_total*dt，不向下取整；original requirement若短于这个更长完整域，必须由真实 owner 在签发前绑定更长 H，不能事后改 receipt。

现有唯一技能调用/控制器执行后若早成功，保持现有真实 actuator hold 并推进剩余步至固定终态，再生成终态观测与 completion receipt；不能读取未来真值调整动作。期间独立硬停止/lease/原D任务deadline照常检查，deadline到达停止并记录 incomplete，不补样本、不算完成。若动作本身已失败，不继续强造“成功末帧”；组件 infinity。原子动作不得因普通策略切换中断，硬停止仍可打断。

一个真实 owner 的 PRE/POST physics-operation hook 在现有 backend observer 汇流处覆盖**每一步**（包括 chunk、render、wait），不可注册第二物理推进者/第二 recorder。D deadline precheck 证明当时许可，postcheck 发现晚返回时保留真实已发生 effect，并禁止成功/后续步。不声称 precheck 消除了任意阻塞间隙、不声称在硬期限前必然完成；正常链验收须真实未过期地到达完整终态。TTL 在原要求的观测消费/提交/后置验证处检查，不能自造“每步都用旧帧重做 native”要求，也不能删现有要求的消费点。

collector 的逐物理步 RGB-D 记录保留 max gap .005S、每个分配帧和完整终态。离线收集可以用独立 development wall 预算，不冒充 native/Tcap。在线沿同一物理控制、完整 H 和噪声/相机域；记录层是否每步保存 raw 要显式登记。任何声称记录层不改变物理作用的适配须 CPU 验证它不 step、不改 actuator/qpos、不引入新控制决策；D 成本差异全部实测且不用于推出 H_D。

## 5. 生产与重建的接口（均为 PROPOSED）

- `vision/native_completion.py` 新增 frozen `NativeCompletionReferenceV2`：schema、recipe_id/hash、skill、object/region、observation_id/hash、compiled_payload/hash、original_owner/checkpoint/binding IDs、policy/geometry/source generation、control_points、reference_kind、full_horizon_steps、physics_dt、capture_step、episode、support_domain_digest。不含 truth，public 构造仅描述。
- 同文件 `resolve_completion_reference_v2(online, contract, step, *, resolved, grounding, role_binding, owner) -> NativeCompletionReferenceV2`；GRASP 从真实本体姿态、RELEASE 从 exact PLACE binding 派生。`NativeCompletionTimingV2` 保存真实 capture/dispatch/terminal event IDs与step、完整分项、D窗口ID、timing_requirement；factory决定 mode，public flag无权限。
- `simulation/mujoco/native_horizon.py` 新增内部 `NativeHorizonSession.from_owner(owner, *, reference, timing)`，`before_operation(kind, step)` / `after_operation(kind, step)` / `finish_action(result) -> ActionResult`。只调现有 robot/backend hold/step，从不另解 IK/选动作/写pose；由现有执行入口和受限 collector 接入，private active capability 校验当前唯一 owner。result保留原controller结果，另记actual steps/hold/effect/expiry，不覆盖原失败。
- `research/native_completion_calibration.py` 新增 `reconstruct_completion_group(registration, group) -> CompletionGroupDiagnostics`、`reconstruct_completion_registry(registration) -> CompletionCalibrationDiagnostics`，读取真实原件与 OC1/P5/P6 lineage。先严格原件校验，再全帧 decoder 与离线真值分离，重算 owner、p/r/x/G/U/L/M/C、全H和组连接图；不信任缓存summary/q/PASS。
- `research/native_completion_calibration.py` 同时定义 `NativeOperationalGroupEnvelopeV2` 与 `read_native_operational_group(registration, group)`：新生产的真实OC1事件/预注册/RESET/owner/完整S分项与原RGB-D、physics、action库存逐一绑定；复用RawV3结构/哈希/物理一致性检查，单独输出旧UTC仍UNKNOWN和新operational source判定。不得把旧reader的UTC缺口整体忽略成COMPLETE、不能将旧原件改scope标签或retrofit为新域。新sidecar由同次真实producer生成，引用每份原件原始SHA与事件身份；未匹配一个必需项即本组件infinity。
- 新 `NativeCompletionRegistrationV2` 字段：schema=`native.calibration.operational.v2`、recipe/metric版本、scope、preregistration OC1事件链、完整 assigned_groups、independence ancestry、sources、scene/camera/marker/noise/asset/controller/grounder pins、八技能 horizon分项/support、age_S=0、timing mode、coverage=.9、max_sample_gap=.005、全部raw inventory。旧UTC registry reader保持严格，不用scope字符串变更给旧raw换域。
- `vision/native_calibration.py` 按总计划新增 `CertifiedNativeArtifacts` 与 `certify_operational_from_application(role_binding)`。冻结不可变数值、注册域、source/registry/app/worker epoch；完整认证一次独立重算所有原件。新 `estimate_completion_operational(..., reference, timing, windows) -> NativeCompletionEstimateV2` 只消费已认证私有实例，热路只重验 source activation generation/current owner/reference/window，不能每次 hash/decode 全raw。estimate含q_joint、scope、domain、recipe、source_digest、reasons，不混入旧motion scalar。
- `vision/action_evidence.py` 新 `validate_native_completion_evidence(...) -> EvidenceVerdict` 接受同一私有source与完整引用；旧 `validate_evidence` unchanged。三真实调用点按 registry schema严格分派，别允许调用方自己传 q/VALID。`EvidenceVerdict.bound_at_completion_m` 可展示q，但附有新的 bound_kind与recipe诊断；旧 VisualEvidence 两个字段仍其原含义。
- `research/native_calibration_collection.py`/`scripts/collect_native_calibration.py` 保持总计划 prepare/collect_once/verify 三接口；`configs/research/native_operational_calibration.yaml` 冻结新recipe。development teacher只给有限技能骨架；动作参数仍经在线像素/本体+同一grounder编译并走同一个控制器/Shield，oracle只生成离线标签。不可用硬编码truth target的旧teacher数据直接证明真实grounder。collector authority固定为 TEACHER_COLLECTION，不接受通用 allow_uncertified 开关；不能授在线native权限。

## 6. 来源、离线资格、热路与真实效果四级

1. P4 活 app factory/worker/lease/RESET/acquisition 因果链提供 source authority；已经结束的 P4 prefix 只说明机制，不能借其 handle。
2. P5/P6 完整窗口与唯一执行/记录闭包；不能用 software descriptor/字符串/PID/hash 授权。
3. 九个新独立组件全量离线重建给有限经验 q 与支持域；旧4807组或本轮CPU不计入。
4. 当前活epoch、当前观测/上下文、精确reference和三消费者均匹配才可热路给 VALID。真实在线新观测与独立物理评分分别判断效果；CPU PASS/finite q/ACK/STOP均不等于真实成功。

禁止范围：真实硬件、外部 UTC迁移、任意动态/20或40mm/S外力、未知grasp变换、marker遮挡/出域、缺fullH、跨episode/复用lease、caller finite、oldraw回填、旧P2结论重写、模拟timeout当wall、改变10mm/5s/1000ms、改变控制器/标记/顶视方案。

## 7. 明确可行性与失败解释

这条路径在逻辑上不要求外部UTC或确定性未来host时间，且给 contact/release 提供可从现有原件独立重算的量，故不存在已证明的时钟逻辑死锁。它仍需真实数据证明 q≤10mm、所有必需可见性、活 deadline 与正常链效果。历史逐步观测已有189 UNKNOWN，不能预计新九组必然有限。首个完整组若重现遮挡/过时/错误/资源失败，保持 infinity与准确原件；停止其余八组，只针对实测根因下一轮，不降低量或移除帧。P3–P6/P7 CPU可继续。

若有人要求硬D期限内完成：没有 H_D来源时只能 UNKNOWN，必须提供对应真实完整执行支持，或由用户明确放弃/改变那项硬完成要求；本轮不提出任意host pause下零超期保证。若用户坚持连续运动supremum替代不了：必须有相应动力学/连续运动证书或明确批准本公开经验终态配方；不得把本计划的统计量说成那种证书。当前已引用原合同允许的S/经验终态域，不因缺无关H_D阻塞正常域。
