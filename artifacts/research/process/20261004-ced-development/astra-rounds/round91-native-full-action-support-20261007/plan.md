# R91 Native Full Action Support Implementation Plan

> **For agentic workers:** 按 `superpowers:executing-plans` 分任务实施；用户指定 GPT-6.1-sol 为软件单写者，ROOT 独立审查并最终提交。此轮实际 GPT-6-astra 仅生成计划，不实施。

**Goal:** 在原阈值和完整时域下，为单机 MuJoCo 正常抓放链建立可生产、可重建、可真实验收的版本化 native 动作支持，解除 P7/P8/P9/P12 的具体来源缺口。

**Architecture:** 旧 P2/UTC/连续速度分支保持；新增明确的完整 S 联合终态经验配方，独立检查 D 窗口。实际 app authority、离线原件校准、已认证热路和真实效果四级分开；同一控制器和唯一 owner 生产真正完整窗口。

**Tech Stack:** 现有 Python、MuJoCo、OpenCV、OC1/OC2、原 RawV3/recording、原独立组件分位算法；不引入依赖或第二控制器。

**Spec:** `docs/superpowers/specs/2026-10-03-rgbd-evidence-research-design.md:82`、继承 dataset spec:23、`2026-10-04-cloud-edge-device-research-design.md:105–114`、原 Astra `clock-dependency-review.md:62–73` 与 operational 补充；准确摘录见 `source-excerpts.md`。具体可执行量、字段、接口、证明见本轮 `design.md`，两者一起审阅。

## Global Constraints

- 本计划写入范围仅本 round。计划运行 tests=0、actual=0、formal=0、Git mutation=0；不复制批量 raw，不 pin 活动 P3/总表/P4 actual输出。
- 0.01m、普通/condition 5s、接收5000ms/外部未来1000ms、最大采样gap .005S、完整H、coverage .9、至少9独立组件、真实50mm/.5S抬升保持、≥1S放置稳定不改。
- 保留原物理资产/顶视相机/可见姿态标记/控制器方案与边缘模型后置；旧P2、历史189 UNKNOWN、原件与失败不变。
- 不把过去速率/平均耗时/timeout/clock resolution/caller数值变成未来来源。不用 all-STOP 或 CPU PASS 关闭 T12；不能宣称机器人硬实时安全。
- P3单写者活动文件不改不pin。P4源前缀和P5/P6独立继续；共享源集成只在 ROOT 移交并冻结其验收版本后由同一软件作者顺序完成。

## 问题、证据及根因

已冻结 `P2/contract.md`、`P2/support-decision.json` 与 `p2-root-final-review` 证明：旧接触参考无 future-motion 来源，固定参考没有 operational 完整校准，缺 future_D 的旧描述保持 UNKNOWN。现源进一步显示 GRASP 在 `reconstruct_truth_endpoint` 返回 None，且重建所有动作要求 target_pose；controller提前返回而 teacher立即下一动作，无法自动提供原完整H；LIFT还有额外 .5S，RELEASE不在旧7技能范围却经过正常native入口。它们是有具体生产/重建断口的问题，不是重新执行测试的失败。

原计时文本严格区分 `v_S` 与 `v_D`。完整H_D是**合同要求完整未来D时的条件前置**；不能继承成所有operational动作门。1000ms是外部帧接收规则。设计据此保留旧门，新增 `CHECKPOINT_D_FULL_S`。它仍需要真实完整H_S、D期限和新版本接触联合误差，绝不是“缺v就放行”。设计在三角不等式层显式记录 drift，并用既有联合经验校准，不声称统计量替代确定性连续界。

输入 26 个限定文件与 SHA256/bytes 在 `input-pins.json`；真实局部读取摘录在 `source-excerpts.md`，工具方法限制在 `read-provenance.json`。无需打印Git巨大stat、重跑旧94/93/799或读取16MB raw来再次证明P2结论。

## Review Focus

1. 公开mode/有限q/copied handle不能选择弱门或授权限；Task1/3 authority反例。
2. 正常链GRASP无target_pose及RELEASE被遗漏，最终“正常”仍STOP；Task1/4真实闭包反例。
3. LIFT额外hold、提前成功、deadline晚返回、WAIT推进漏出完整H；Task2逐项反例。
4. 帧遮挡/failed组/组件共享被删掉，或八个.9误称联合.9；Task3重建反例。
5. 三入口只接线一处、Shield后目标变更、effect使用旧帧；Task4逐入口反例。

## Task 1：冻结新配方与纯CPU数学闭包

**Create:** `src/cloud_edge_robot_arm/vision/native_completion.py`、`tests/test_native_completion_v2.py`。**Modify:** `vision/native_references.py` 仅显式新schema分派（旧函数语义不变）；`vision/native_calibration.py`新registry类型入口。根目录均为 `src/cloud_edge_robot_arm/`。

**Interfaces:** design §5 的 `NativeCompletionReferenceV2`、`NativeCompletionTimingV2`、`resolve_completion_reference_v2(...)`、`NativeCompletionRegistrationV2`。所有类型仍描述数据，authority来自后续私有工厂。

- [ ] ROOT 逐条签收 design 的时域条件解释、新metric、八技能闭包和更长H；保存 activation，重算26输入，列 P5/P6未来接入待绑定项，不伪称未实现接口已存在。P3活动源不加入旧pins。
- [ ] 写12个固定case的 `test_contract_case`：`sd_conditional`、`external_future_rule`、`joint_triangle`、`not_continuous_speed`、`grasp_without_target_pose`、`release_exact_place_binding`、`fixed_reference_not_body_speed`、`capture_step_zero_age`、`full_horizon_lift_hold`、`caller_mode_rejected`、`foreign_owner_rejected`、`public_finite_q_rejected`。
- [ ] 一次命名RED，保存原命令/exit/JUnit/stdout。预期缺新接口或正确新断言失败；不能用无关import/环境失败充RED。
- [ ] 实现 design §1–3/5 的版本化类型和计算；三角关系固定例 U=.002,L=.003,M=.004 => C=.009；M缺失不能为0；只有fixed精确参考M=0。
- [ ] 同12case GREEN一次；owned Ruff/format/type检查仅新/改源。现P2两类核心旧语义用最后Task4的兼容node统一检查，不重跑旧套件。

## Task 2：真正完整H生产与唯一执行闭包

**Create:** `src/cloud_edge_robot_arm/simulation/mujoco/native_horizon.py`。**Modify:** `simulation/mujoco/skill_robot.py`、`simulation/mujoco/backend.py` 在既有单owner/operation observer汇流处接入，不增加第二观察器/执行者；`vision/execution.py` 现有实际调用前后；`research/native_calibration_collection.py`（总计划新文件）collector同一机制。**Tests:** 同 `tests/test_native_completion_v2.py` 的horizon cases及下Task重建8cases。

**Interfaces:** design §4–5 的 `NativeHorizonSession` 和带分项的 `HorizonBreakdown`；原动作结果另存，延长hold明确记录actual steps，不把早success当新终态。

- [ ] 先用无渲染CPU fake operation journal证明整型step预算：ceil不截短；LIFT内置.5S不能遗漏或双算；RELEASE需真实1S稳定区；controller早返回后仍不得下一动作。
- [ ] 在现有控制器返回路径增加真实hold至绑定终态的生产过程，硬停止/原deadline保留；超界/失败保留partial而不是伪终态。原控制器、参数、IK、force和pose不改。
- [ ] 将 P5/P6验收后的当前 owner/clock/hook接口接入。它们尚未可用时保留独立CPU交付，禁止用已结束P4 prefix的owner；不与并行P4/其他作者同时改共享源。
- [ ] 确认每一步pre/post真实D，晚返回留effect而失败；同一S期间render D耗时入账；禁止普通事件切换原子动作。别新增“每步用旧观测重做TTL”伪前置，消费点仍按原合同。

## Task 3：独立校准、原件重建与热路认证

**Create:** `src/cloud_edge_robot_arm/research/native_completion_calibration.py`、`tests/test_native_completion_calibration_v2.py`。**Modify:** `vision/native_calibration.py`（operational registry/私有certified分支）；`research/native_geometry_calibration.py`（复用原geometry/component纯函数，新schema dispatch，旧UTC路径不动）；`research/native_calibration_collection.py`、`scripts/collect_native_calibration.py`、`configs/research/native_operational_calibration.yaml`（依总计划P7创建）。

**Interfaces:** design §5 的group/registry重建、prepare/collect_once/verify、`CertifiedNativeArtifacts`、`estimate_completion_operational`；旧 `NativeCalibrationSource.estimate(now=UTC)` unchanged。

- [ ] 写8个固定case的 `test_reconstruction_case`：`exact_full_horizon`、`early_success_no_next_action`、`late_effect_preserved`、`grasp_contact_decomposition`、`release_whole_body_stability`、`unknown_component_infinity`、`shared_ancestry_one_component`、`hot_path_generation_no_raw_io`，先命名RED再实现/GREEN，各一次。
- [ ] 独立读原OC1/P5/P6事件/source/owner与所有分配帧、8动作、fullH/control points，重算G/U/L/M/C。旧v1 summary、q、PASS和caller dict不作认证来源。
- [ ] 组分数先全必需动作联合max，缺一项infinity；原独立组件连接规则不放宽。n9/rank9与.9不变；输出每项分母及missing/UNKNOWN/infinite原因，未采分配组也是未完成。
- [ ] 启动完整认证仅一次；不可变深拷贝artifacts+代次私有seal；热路只读当前source代次/owner/window/ref，不全raw hash/redecode。source/registry activation变化强制重新认证，公开对象/序列化handle不授权。
- [ ] collector用新app-owned TEACHER_COLLECTION能力，有限教学骨架+实际像素/本体grounder+原Shield/控制器；真值仅离线标签。真实source authority≠native执行资格，避免必须先有自己校准的循环依赖。

## Task 4：三调用点与真实正常链入口

**Modify:** `vision/action_evidence.py`、`vision/execution.py`（现1485/1561两处）、`repositories/event_autonomy/visual_verification.py`（现870一处）；必要返回诊断字段在 `edge/evidence/models.py`追加兼容默认字段，旧validator公式不改。**Create:** `tests/test_native_completion_routes_v2.py`。

**Interfaces:** `validate_native_completion_evidence(...)`，严格按工厂注册schema分派；新q只能在 `JOINT_COMPLETION_V2`路径消费。其余身份/深度/标定/条件/Shield与提交/事务/dispatch闭包沿P5/P6。

- [ ] `test_route_case` 三参数：`pre_submit`、`post_shield_dispatch`、`repository_effect`；每项同时断言全来源合法控制可达 VALID、旧帧或owner/payload变化拒绝、真值不可在线访问、effect必须新证据。
- [ ] `test_legacy_p2_unchanged` 一个node检查旧mutable reference仍None、旧fullfuture诊断UNKNOWN、旧UTC缺源仍拒绝、fixed v=0不代表controller/body0；仅此限定旧语义回归。
- [ ] RED→最小接入→GREEN；正例只标CPU控制，不冒充真native。跨P5/P6闭包的更广实际验收仍其原计划，不凭此24node重复申领实际。
- [ ] ROOT不同作者审查静止源/接口/全部24node结果与独立重建；只在新变更/失败时增加有关检查，不复跑旧94/799/RED序列。

## 软件验证预算和交付

新增明确24个pytest node（12合同+8重建+3入口+1旧语义）；允许每个task所属node一次RED和一次GREEN，已批准预期RED继续，不出新Astra。Task2涉及的horizon断言并入上述固定case，不重复跑实现镜像测试。每个静止版本一次owned静态和一次不同作者审查；新根因/计划外失败暂停相关任务再Astra，独立工作继续。

命令以冻结node manifest为准：`.venv/bin/python -m pytest -q <本任务完整node IDs> --junitxml=<新目录>`；输出路径不可覆盖。实施后保存 exact source/命令/exit/原日志/分母和步骤报告。ROOT按实际变更明确路径交付，R77/R81隔离祖先及原件空白规则延用，正常non-force push、local/upstream/live三SHA；不发布本轮读过的全部输入/raw。

## 最小新实际实验：明确阶段预算，不在计划轮执行

**前置：** ROOT接受新配方；P3静止source绑定、P4机制已真实验收但重新启动自己的live owner；P5/P6全闭包软件和要求的真实生命周期证据适用；独立审查24node与collector、完整source/asset/camera/noise/grounder/recipe/assigned inventory；串行renderer；无旧raw复用。外部真实模型费用仍其单独既有授权/预算，collector不新增付费调用。

1. `prepare_native_calibration`冻结9个从未查看的独立组件及各一次attempt，完整动作骨架 MOVE_ABOVE→APPROACH→GRASP→LIFT→MOVE_TO_REGION→PLACE→RELEASE→RETREAT，最后完整稳定验证。每动作真实重观测/编译与原deadline；teacher scope只产校准原件。该顺序若与已绑定原合同实际顺序不一致须在activation明确唯一采用原合同顺序及相应postcondition，不能边跑边改。
2. 先只执行编号001完整组一次并独立重建。它是预登记9组中的第一组，绝非预试后丢弃；失败保留且该组件infinity，不采其余8、不自动retry。首组成功只证明可生产/重建，n1仍无有限.9认证。
3. 首组全链/完整可见性/资源/时域均满足后，由ROOT逐组激活余8，一组一次，满9全部保留。不得循环追加直到有限，不拿历史4807/CPU/P4prefix凑组。任何新失败先原件+新Astra。
4. 九组q≤.01且域完整时，在独立新scene做一次真实在线完整正常链smoke（不能用teacher+oracle），三消费者原件、实际D/S/原TTL/deadline、online效果及独立physical score全部验收。这是P8的1个新smoke，不能兼作第10校准组、P9或P12成功分母。失败不是完成；修复后另计划新attempt。

**有界预算：** calibration最多9attempt（先1后8），native smoke最多1attempt；无自动重试。每组原120SETTLE；动作H逐项从真实owner派生，不能为节省数据把10S合同截成观察到的3S。初始准备限总S≤80、总physics/RGB-D分配≤20,000（每步保留，gap≤.005）、wall≤5,400D秒、实际落盘≤32GiB；这些是开发采集资源停止上限，**不是 H_D证明或Tcap/Rcap**。prepare须从exact dt/H/内置hold/settle计算最坏step数，任一不适合上述界在运行前 STOP并报告，不能改动作阈值或偷偷放大预算。按每组cap及已有保留资料做本地磁盘预检、预留失败flush空间；不以旧压缩平均保证磁盘。全部9组最坏288GiB、13.5小时为上限而非预计支出，首组后才决定继续；若资源不足明确这个实际阻塞。新在线smoke严格使用自己已绑定原task/Tcap/恢复Rcap，不借collector的5400秒。

必须保留每allocated group/attempt/frame/action/effect/condition、未执行后缀、所有partial/failure与原输出、完整序列/hash。逐步记录不会因此证明连续速度；source/软件/实际统计分级报告。P9 INITIAL等原门、P12预登记32episodes及前两正常组正链不因本轮改变；不另预算重跑它们。

## 验收与失败边界

- 软件完成：24精确node、owned静态、独审、逐路径交付；actual仍0。
- 来源/一组：真实完整生产/独立重建可用，统计仍不可用。
- 校准：9独立组件联合q有限≤10mm且当前source/app域真正认证；不代表G1/P12/formal。
- 正常正链：独立在线smoke真实提交、fullH完成、在线新效果与独立50mm/.5S/释放1S稳定成功，所有TTL/deadline及三入口原件可复算。缺任何一项不关闭阻塞。
- P12最终仍按原32episode/正常组要求，不能把全STOP变成完成。原连续v/显式futureD路径仍无来源时UNKNOWN，不阻塞适用新S合同的正常域；硬件和外部UTC不支持。

ROOT如不接受新联合终态配方，必须具体指出是否坚持连续v或硬futureD要求；这时确需该种真实支持来源或用户改变相应要求，而不是无限重复UNKNOWN检查。若接受而首组出现真实误差/遮挡/超时，则依据准确原件下一轮修复，P3–P6/P7 CPU不连带停工。

## 自审

已逐项覆盖规格量词、外部1000ms、S/D单位、目标参考与body速度、GRASP/RELEASE、LIFT额外hold、所有分母、.9联合量、原可见性限制、单执行器、源/权限/热路/效果分级、P4–P6依赖与实际资源。没有把未来H_D假设换成概率或无出处添加任意hostpause保证；没有宣布新经验配方已经实测支持。所有提案均标PROPOSED；旧P2结论保持冻结。
