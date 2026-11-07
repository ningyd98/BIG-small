# R453 — 必需命令/控制/物理/采集/guard来源图重建

实际 gpt-6-astra，2026-11-08；仅规划，0产品修改/测试/physics/render/model。原证据为whole-change-review F3/F4与冻结源码27pins。

同根因依据：现reader只检验同一小片原件内部/冗余日志彼此一致，未建立“命令必须产生何种控制、每个真实effect必须有什么操作/guard证据”的必需边。F3/F4需要同一跨记录图；F1 sentinel与F2/F5观察者失败已分别R451/R452，不混入本修复。

## 依赖、范围与实现结构

R451和R452各自限定GREEN通过后才实施。原27pins仍为三轮共同初始snapshot，intake不可覆盖。ROOT逐路径审查已批准R451/R452 diff和step-report，将原SHA/当前SHA/授权plan与报告SHA写implementation/applicability.json；只有这些批准差异可接受，其他漂移停止。共享helper为tests/native_collection_source_graph.py。

允许新reader、新recorder、新纯模块 `research/native_source_effect_graph.py`、共享helper、新tests/test_native_effect_graph.py及reader旧软件fixture的必要适配。app的R452代码本轮仅可最终格式化，不新增行为。旧raw_episode_v3.py、raw_recorder_v3.py、backend/camera/guard/native_horizon均只读。不要为了复用legacy总验证器伪造UTC映射或把其UNKNOWN过滤成PASS；将所需命令replay/图检查集中到新纯模块，由_Audit.physics/operations显式调用。

## A. 必须保留的原CONTROL来源

现RawV3只将CONTROL结果嵌入随后PHYSICS记录，终止emergency_stop内部CONTROL没有随后PHYSICS，因此无法从现physics列表恢复。新recorder在实际CONTROL END有完整result时原样保存一个有界 `control_sources` 列表：operation_id、对应operation-N interval_id、event episode_id/当前physics_step、完整实际control_state。不从命令或下一physics合成。每ID最多一份，失败或重复保留原失败；每次guard正常完整run最多N个逐步CONTROL加1个STOP CONTROL，容器硬上限原physical_budget+1，无截断或无限list。失败case超上限仍PARTIAL，不拿预算解释缺原件。

保存放在可失败持久化之前的实际事件处理，最终freeze同库存输出；沿R452计账/失败保持，不改变camera或observer行为。每个physics.control_payload必须与它control_interval_id所引用的这份原CONTROL完全相等。终止CONTROL的control_state.physics_step为N+1，但event/interval当前step均N；**这是控制面预指向下一步，不是实际多了一步physics**。

## B. 命令到控制的确定性重放

按原命令seq与CONTROL操作先后重放，起始状态来自真实RESET.initial_controller_targets（7 joints/2 fingers）、actuator_delay_steps与reset.physics_state，验证有限数值/维度、非负整数delay及同一episode；与登记的reset/config/无未登记fault来源一致。初始arm targets应对应实际reset的关节初值；finger目标是现注册open control .039，不能把reset measured .04误当control target。

每个命令校核：command_seq连续、payload seq/episode一致、当前S存在、sim_time对应state[S]、COMMAND interval在S开始/结束，实际parent purpose/action与原range对应；accepted/rejected/after_emergency_stop与真实stop latch一致。所有命令（包括最后无下一physics的STOP）都验证effective_from_step：accepted普通/gripper/hold/stop为S+1，accepted joint为S+1+delay；rejected为null且无目标影响；queued reason中的available step等于S+delay。不得跳过没有后续physics的尾命令。

joint请求裁剪到[-2.8,2.8]必须等于actual applied_target；有delay则按真实顺序排队，在CONTROL当前S满足available≤S时生效，多个同step命令仍按原seq顺序。hold_current_joints必须目标等于派发时state[S].joint_positions_rad，actual applied等于同值，并清空pending arm队列。gripper open/close目标分别为(.039,.039)/(0,0)，不得由实测手指位置猜目标。拒绝命令不能改变状态。

对每个CONTROL（包括终止CONTROL）验证重放arm/finger目标与actual payload、control计算方程、pre joints/bias/gain/ranges、episode/currenttime完全一致。逐步CONTROL是S=n-1、payload target-step=n；CONTROL interval必须CONTROL_APPLY、start=end=n-1，且真实OC1操作先于该PHYSICS begin。每步PHYSICS的control_interval_id不得指向别步、重复旧CONTROL或终止CONTROL。HOLD期间不能有未登记的新目标；即使同时修改applied target与方程输出、普通hash全部重算，仍必须因原命令重放不一致被拒绝。

不直接拿legacy全验证结论授予资格。参考冻结 raw_episode_v3.py1316起的目标/延迟/clip/hold/gripper规则，保留legacy UTC mapping UNAVAILABLE及nativeUNKNOWN，使用原OC1操作证据检验时序。

## C. 来源图覆盖：不能只比较两份日志

以primary原件反向推导必须存在的节点：唯一RESET；每个physics row的PHYSICS与CONTROL；每条command的COMMAND；每个allocated frame/frame_sources/capture_source_roles的CAPTURE；以及终止额外CONTROL。将它们与全部operation intervals、operational_events和backend_operation_ledger做双向多重集合/唯一性对应，逐个operation_id/episode/kind/S校核，并按真实BEGIN/END顺序验证嵌套/闭合、无孤儿、无额外未登记操作、无ID重复/丢失。不能删除冗余两边同一行后仍满足primary图。

旧recorder的RESET没有RawIntervalV3行，这是实际source约定：RESET通过唯一原reset result/metadata和RESET操作对应，不能要求凭空生成RESET interval。RESET BEGIN episode可能为None而END为本episode，也须按原源允许这一个初始化过渡，不能把所有episode差异豁免。

CONTROL_APPLY、PHYSICS_STEP、COMMAND、ACQUISITION分别匹配backend CONTROL、PHYSICS、COMMAND、CAPTURE；其他purpose/action intervals继续原验证。全部CAPTURE包括reset隐式、step末隐式、逐physics显式和action boundary显式；implicit必须2passes/空instances，不得以缺实例丢弃。操作阶段在geometry之前，不能依赖尚未填充的self.frames：从已校验库存的source-frame元数据读取所需ID/role/S；后续geometry继续验证完整字节/图像hash/实例/数量。不要因此跳过metadata或读整个RGB两遍来实现简单ID索引。

每份control_sources对应一个CONTROL操作；恰N份对应physics加最后1份对应终止内部CONTROL。若存在failed source，仍PARTIAL不能通过complete路径。完整normal路径至少有一个实际physics；小软件图用于此语义，不冒称12960 full-H。

## D. 准确guard语法与真实终止

必须按冻结backend源码实际发出的语法重建，不可创造“每CAPTURE都必须有guard pair”的假规则：

- 普通joint/gripper COMMAND与逐步CONTROL，各有一个本kind BEFORE、一个AFTER和操作结束后的RETURN AFTER。
- 每个有observer的PHYSICS同时经过decorator和内层advance检查，因此BEFORE×2（S=n-1）、AFTER×2（S=n）、再RETURN AFTER。相同字段的两次检查是两条真实事件，不得用set去重。
- 每physics的三pass sampler有CAPTURE BEFORE（引用刚结束PHYSICS的当前operation_id）和CAPTURE AFTER（引用新CAPTURE id）。普通显式boundary与隐式cache采集由实际source/OC1/current owner约束，不虚构不存在的CAPTURE guard。
- 每次backend.step调用有RETURN BEFORE与RETURN AFTER；step完成时的implicit cache CAPTURE界定这次调用的尾部，reset内implicit除外。按操作顺序/每步capture role恢复step call分组：组首CONTROL之前的RETURN BEFORE引用上一个已分配operation id；组末implicit后RETURN AFTER引用该implicit id。组内没有新普通命令，逐physics显式采集恰对应每一physics。不得只检查RETURN总数而忽略位置/step/identity。
- normal关闭在最终N后有唯一CLOSED；它本身无ordinary sequence/callback，不当作active-check。它发生在safe STOP命令之前，不能要求不存在的stop guard callbacks。

建议纯模块对有序操作与capture roles生成expected guard checkpoint序列，再与每个non-CLOSED原guard逐条比对kind/phase/episode/operation_id/S与sequence连续性、outcome=ALLOWED、无error/stop_error。对操作内部的BEFORE/AFTER以原OC1 bracket与active current读数验证位置；RETURN AFTER在其操作END之后、step RETURN BEFORE在组首CONTROL之前。不得把实际doublePHYSICS缩成一对。

active-checks必须非空并与non-CLOSED guard按顺序一一对应（包括重复字段的事件），checkpoint全部字段、step、lease_id、原OC1 domain/deadline均匹配；不能只对已有check循环、容许缺项。每条检查仍使用现原owner/current/lease约束，不凭新的caller allow字段授予来源资格。

完整normal关闭还必须有实际尾部 **hold_current_joints → emergency_stop** 两条accepted COMMAND，当前S=N、原TERMINATION purpose、没有owner action，hold target来自state[N]并清队列；emergency_stop内部恰一个CONTROL_APPLY，嵌套在该COMMAND中，target为真实hold/finger目标，control_state目标step=N+1但不推进physics。最后不能有physics/普通accepted命令。CLOSED只有标签、STOP缺失、顺序颠倒、缺任一command或internal CONTROL均拒绝。safe hold/STOP/internal CONTROL实际没有普通guard，所以仅对这个准确可定位闭合来源豁免，绝不能对全部CONTROL或用户伪标记STOP豁免。

## E. 软件图与测试预算

新pure模块提供 `validate_native_source_effect_graph` 的稳定入口（参数可用结构化raw/操作与active checks/protocol）；新reader必调用，函数只返回诊断/抛拒绝，无权限字段。共享helper扩展为真实backend dispatch/control/observer wrappers、NativeFullHorizonRecorder和原guard闭合生成的短CPU图；fake engine仅更新软件S/time，fake camera仅返回注册形状原字节，不初始化MuJoCo/render。RESET、至少两个step调用（覆盖多physics一个step与单physicsstep）、延迟joint命令、gripper、HOLD、逐步与隐式capture及TERMINATION都实际经过既有方法。guard/checks由真实callback调用记录，禁止手工拼一份“完美日志”替代source。

五个新节点与展开spec在plan.json：

1. 正常完整小图经过reader physics+operations/新kernel；保持SOFTWARE_ONLY、legacyUTC UNKNOWN、无full-H/native资格。
2. 命令变体循环：初始target变动、clip不符、effective step/queue reason、delay、gripper、hold目标、hold未清pending、同步改control target+方程输出；每个应在对应语义边拒绝。保留原source graph另存，派生篡改图可重算软件file hash以证明不是仅checksum拦截。
3. 同时从operational_events与backendledger删除CONTROL/PHYSICS/COMMAND/CAPTURE的配对行，或删primary-ref与重命名ID；未删的必须primary来源/固定日程仍使其拒绝，不能因两边相等通过。
4. guard/check变体：仅CLOSED、缺一对/重复PHYSICS事件、empty或少一条active check、伪phase/step、缺RETURN/逐步capture pair、缺hold/STOP/internal CONTROL、交换终止命令、终止后effect；全部拒绝。合法safe exemptions正例通过。
5. cross-episode/control_interval跨step、CONTROL晚于PHYSICS、operation嵌套错/未闭合、orphan metadata/frame/capture role、COMMAND parent/seq/terminal物理计数错误等primary图边拒绝；配合R451背景与R452accounting原件保持真实字段。

唯一graph-red在实现前写五节点并显式检查新kernel API，预期恰5个缺API assertion失败，不允许import错误；GREEN必须继续执行上述真实图/变体，不能止于API存在。唯一graph-green5PASS，child180s/outer300s。不另外做probe或重复宽回归。

随后仅一次全批准改动文件format实现，然后scoped ruff/format/mypy各一次（child120s/outer240s）。唯一final-focused跑R451/R452/R453三个新测试文件及native_collection_authority、native_full_horizon_originals、native_calibration_collection、native_archived_tracker；child300s/outer420s。它覆盖本轮实际改过的生产者/reader/失败cleanup/历史时间重放/源码登记，不重复旧未变backend全套或230项全回归。各文件/命令/env/fresh basetemp/events/JUnit路径见spec；最终实际计数来自本次事件，不单独collect-only；无actual节点。不要对同一个final gate改名再跑。

全部阶段顺序执行且attempt1；任何计划外失败/新根因/范围扩大停止依赖修复和actual并新Astra。保存各phase step-report、原stdout/JUnit/result、前后SHA/diff，保留R44986PASS与所有旧失败，不冒称旧结果为当前整仓覆盖。

## F. 复核与未来原运行续接

final-focused与静态通过后，让已经完成whole-change review的同一reviewer只核验F1–F5修复、source语法和授权范围，不再委派第二个fresh whole审查；其新发现仍按AGENTS。本计划不自行发送消息或spawn。

创建新的R439未来runner/commands-r453/source-overlay：包含R449及R451–R453准确批准路径、各前后SHA、原baseline/commands SHA、适用性与phase报告、最终source inventory。仅覆盖未运行的prepare/full/read，所有历史commands/results/spec原样保留。freeze fresh prepare生成新协议世代，之后full/read源不得漂移。source graph修复不改变controller、pose-marker、camera、EGL、普通TTL或clock来源。

实际仍仅原seed439001一次，12960physics、explicit≤12976、implicit≤12962、render≤64852、wall1800/outer1920、RSS8GiB、raw16GiB。全软件及scoped review通过、R450显式用户服务授权与资源条件满足后才放行；R450等待期间不停止服务。本轮0新增actual/模型请求/组数，不自动扩到九组。physics失败/原件缺失/reader拒绝均保留PARTIAL/UNKNOWN，不以source校验通过冒充native/正式研究验收。

自审：根因分轮明确、共享原件已冻结、语法忠于旧backend（含doublePHYSICS与STOP CONTROL例外）、短软件图来源真实、验证有界、旧UNKNOWN与实际额度未改变。
