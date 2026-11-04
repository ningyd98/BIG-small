# R424 毕业设计下一阶段准入评估

本评估由实际 **gpt-6-astra** 在HEAD `78f36fbaf43d6bbe3b50c40d09097f75895d72ab`只读完成。**现在可以继续T3b/T7b受限开发及原5项租约有界诊断；不能据此进入未经当前证据验收的B0真实筛选、INITIAL、METHOD、FINAL或正式实验。** 不要求先把4751全部转绿或清完所有格式告警。重点应回到独立证书生产、native消费者和实际方法来源接入。

## 当前能确认的证据及日期

- R413的11月3长测针对`ab18abd0f82a024b62f4423c946c6585f8d18c65`：4751软件节点一次STARTED=4709P/35F/6skip/1INCOMPLETE；ETEAC/PCSC原生MOCK自然结束；浏览器42P/1原skip。它比权威页11月2快照更新，旧ETEAC/19浏览器待办不能继续当未解决事实。来源：R413 `reports/development-progress.md`。
- R419—421已补外层回执真实性/指标资格隔离、SQLite显式close与模拟旧lease归档，定向42P；生产默认MOCK+RGBD仍如实BLOCKED，测试专属LEGACY正对照不改变生产输入意图或正式资格。来源：R419 `phase-summary.md`、R420/R421 `step-report.md`。
- R422仅修测试前置契约：原22到原断言、47定向P，406 src原字节未变。新全量没有重跑，不能35−22或再减42计算全量。来源：R422 `phase-summary.md`和`validation-summary.json`。
- 当前`configs/research/ced_roles.yaml`默认`profile_id=null`、`available_model_ids=[]`；规则provider的dispatch/local_recover=false、status=NOT_ACCEPTED。selection/foundation配置episodes=120，pools/role_probe/selection_evidence/protocol_evidence全null、默认dry。这仅证明checked-in默认未绑定，**不证明用户运行store无key或没有CLI override**。
- 当前`vision/action_evidence.py`明确缺独立几何/运动证书，`native_action_contract`仍给两界None；`scripts/run_rgbd_pilot.py`的power分支即使INITIAL/method文件存在仍追加“method runtime and actual power source acceptance are not integrated”。因此后面仍有实际生产/消费接口研发，不能简化成补配置跑一次。
- 当前`research/freeze_evidence.py::_initial_v2_spec`要求独立完整resource-plan、合格120foundation、相同pool/roles/周期selection、完整protocol-evidence及Tcap/role一致；这是一项门禁实现事实，不是已有真实INITIAL证据。

- 已有native_calibration模块与规则/来源软件测试，并非完全没有证书软件；但APPLICATION_INDEX_PATH固定索引当前ABSENT_OBSERVED、device_source_paths未登记，该类from_application要求实际rolebinding锚定。execution实际提交调用native_action_contract，当前两界仍None。需要独立实际来源与生产消费者接入；测试隔离fixture和调用方伪VALID不获动作准入。

## 放行/暂停矩阵

| 阶段 | 证据层级与当前状态 | 有界最小下一动作 | 验收出口 | 不能宣称 |
|---|---|---|---|---|
| A1 本轮租约诊断 | SOFTWARE_ONLY；原失败＋当前源码静态；**READY_FOR_BOUNDED_DIAGNOSIS** | 5原节点各一次新进程零重试，最多1guard握手/预初始化对照探针，≤300秒，保留三阶段和owned出口。 | 按H1/H2/H3逐项给真实trace、原始输出与置信边界；修复另轮。 | 不能称5项已修复、全量通过或真实闭环验收。 |
| A2 下一步T3b/T7b受限开发 | 当前checked-in源与配置；历史开发证据；**GO_LIMITED_DEVELOPMENT** | 按现有接口定位独立证书生产→native消费者及实际角色/来源绑定的最小缺口，读取非秘密状态和已存在报告；具体新缺陷先Astra限定轮。 | 一个有边界的接口/证书消费者交付，真实拒绝和UNKNOWN保护有效，相关定向验证与来源hash可审查。 | 47P或全4751绿都不替代物理、Max、INITIAL；无需先清空所有format告警。 |
| B1 T3b 当前Max角色实际探测 | 历史REAL_VLM35请求；当前默认配置未绑定；**HOLD_ACTUAL_RUN_PENDING_CURRENT_BINDING** | 另轮读取用户指定的非秘密profile/CLI override及来源快照，确认真实服务、付费授权与预算；不在R424探API/secret。满足后按冻结probe计划一次有界新探测。 | 当前源/配置的双图实际wire、结构化解析、目标缺失拒绝、取消/晚到边界、角色/模型/source hash通过独立核验。 | 历史35HTTP200或available=true摘要不能证明当前通道/规划可靠性；默认profile=null不能证明运行store无key。 |
| B2 T7b native端侧及受限真实仿真闭环 | 软件与历史REAL_CAPTURE；当前native界显式None；**HOLD_NATIVE_ACTION_ACCEPTANCE** | 复用已有native_calibration软件，补独立实际校准来源→冻结应用索引/rolebinding→实际native消费者→连续效果证据；当前固定index缺失、native两界仍None。动作开始前需VALID，不能用伪VALID或开发fixture放行。 | 同episode真实新RGB-D/标定/来源，非oracle在线证据；独立几何/运动覆盖与时域证书，≥50mm抬升≥0.5秒保持、释放后≥1秒完整放置稳定；actual actuator/step和独立物理重算一致，UNKNOWN保留。 | 单帧OBSERVED、4807帧可见、教师成功、模型置信度、TCP升高或写目标位姿不能替代连续物体效果；不是实体机器人放行。 |
| C1 T8a 四周期B0 selection | 旧2秒120组5成功/静态4/40；新默认证据路径null；**HOLD_UNTIL_T3B_T7B_CURRENT_ACCEPTANCE** | T3b/T7b当前证据通过后，独立120 selection组（12层各10）配对扫描0.5/1/2/5秒，保留全部480周期-组结果和失败。 | 候选静态≥90%、整体≥80%、安全违规≤1%；合格中云请求最少，平局墙钟低；全不合格NO_FEASIBLE_BASELINE，未完INCOMPLETE。 | 旧2秒失败不等于四周期都不可行；不选弱基线或先宣称云请求节省。 |
| C2 T8a固定机会/200离线故障 | 历史100采集/1教师；完整证据未验收；**GO_PREPARATION_HOLD_COMPLETE_CLAIM** | 固定机会候选/标签规则与200故障eligibility/有界生成协议；开发与正式来源隔离，另轮实际生产和独立验证。 | 完整固定机会可从原始传感/几何/时刻重算；200实际注入、教师恢复与独立成功/安全证据，全部尝试/失败/排除保留。 | 不等待在线T13，离线可恢复不等于在线G4；1组不能冒充200，正式标签不作视觉开发输入。 |
| C3 T8b foundation与INITIAL | 当前源已有严格冻结检查；无本轮实际新foundation来源；**HOLD_INITIAL** | selection合格后另120未用组foundation；独立审计实际raw/帧/物理/成本及完整资源计划，绑定相同role/pools/周期和完整protocol-evidence。 | foundation复现静态≥90%、整体≥80%、安全≤1%；Tcap=成功P99×2向上10秒取整并夹[120,600]，Rcap60；独立预算与机会/200故障、源hash一致，INITIAL CLI实际接受。 | YAML/目录/摘要存在不等于冻结；INITIAL不选正式N、不等于FINAL。 |
| D1 INITIAL后T9→T10→T11→T12a→T13 | 多项软件独审历史；实际风险/方法/恢复未接受；**GO_INDEPENDENT_SOFTWARE_HOLD_METHOD_ACCEPTANCE** | INITIAL后在隔离train/calibration/selection真实来源校准风险，接证据/提交复核、共同公平基线与规则成本provider；再接验证后恢复和最小未完成后缀修复。 | 共同云/端/provider与预算冻结、模式CAS与owner源一致；LOCAL_RECOVER仅能力验收后开放，持久有界预算、ACK/接受/启动/效果分开、已完成动作不重放。 | 软件链完成不等于METHOD；T7b基础证书不等待T9回填；边缘型号后置不取消判断层。 |
| D2 方法冻结/独立120功效/FINAL/正式N | 当前power入口显式not integrated；正式NOT_RUN；**HOLD_REQUIRES_IMPLEMENTATION_AND_REAL_EVIDENCE** | 开发实际method runtime和power来源消费者；先冻结完整方法/provider，再用另120互斥组只估功效，完整预算与INITIAL链接独立验真。 | 按α=.05、power=.8/Holm确定N∈{600,1200,1800,2400}；所需N>2400为INSUFFICIENT_EVIDENCE。FINAL及G0/G1条件通过后才运行正式N、固定机会和200恢复，全分母统计。 | 不是补配置即可跑power；不能先正式跑再选择N或调参，旧5580 PHASE12_REJECTED不自动恢复资格。 |
| E 外围软件债务/可选扩展/硬件 | R413历史长测与R419-R422定向；硬件无验收；**DEPENDENCY_SCOPED_BACKLOG_HARDWARE_LOCKED** | 与被开发入口直接相关的租约/回执/API/事件来源缺陷先收口；格式治理、Isaac/G5/腕相机/边缘型号独立排队。 | 每项有新鲜定向证据和明确范围；实体路线须独立立项现场安全审批。 | 不要求清空4751/全库format才开展T3b/T7b；UTC4502.509秒未达600线仍保留，不能放宽阈值；真实硬件NOT_STARTED、S3/S4 LOCKED。 |

## 每行依据

- **A1 本轮租约诊断：** `intake/original-lease-failures.json`；`tests/test_rgbd_lease_handoff.py`；`src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py`。
- **A2 下一步T3b/T7b受限开发：** `docs/roadmap.md`；`src/cloud_edge_robot_arm/vision/action_evidence.py:1-6,42`；`configs/research/ced_roles.yaml`。
- **B1 T3b 当前Max角色实际探测：** `docs/current_authoritative_status.md:54`；`configs/research/ced_roles.yaml`；`docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md:T3b`。
- **B2 T7b native端侧及受限真实仿真闭环：** `src/cloud_edge_robot_arm/vision/action_evidence.py`；`docs/research/results_and_limits.md`；`docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md:46-54,118-123`。
- **C1 T8a 四周期B0 selection：** `configs/research/ced_selection.yaml`；`docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md:T8a`；`docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md:112`。
- **C2 T8a固定机会/200离线故障：** `docs/research/results_and_limits.md`；`docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md:68-82`。
- **C3 T8b foundation与INITIAL：** `configs/research/ced_foundation.yaml`；`src/cloud_edge_robot_arm/research/freeze_evidence.py:881-936`；`docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md:T8b`。
- **D1 INITIAL后T9→T10→T11→T12a→T13：** `docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md:T9-T13`；`configs/research/ced_roles.yaml`。
- **D2 方法冻结/独立120功效/FINAL/正式N：** `scripts/run_rgbd_pilot.py:665-676`；`docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md:T15b-T16b`；`docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md:116-127`。
- **E 外围软件债务/可选扩展/硬件：** `docs/roadmap.md`；`docs/research/results_and_limits.md`；`artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/development-progress.md`。

## 仍缺的当前状态证据

1. 截至本轮未读取运行model store、secret或CLI override；当前profile选择、服务可用性、计费授权/预算与role/source绑定均需新非秘密状态证据，不能沿用旧无key结论。
2. 没有本轮新Max双图probe、T7b独立几何/运动证书或连续效果验收；当前native_action_contract的两界仍None是可直接核验的实现缺口。
3. 没有本轮新完整固定机会/200故障与四周期selection/另120foundation/资源预算/INITIAL报告；历史1组/100采集只描述原报告口径，不冒充11月实时完整inventory。
4. 功效入口明确未集成，实际method runtime/power source验收需要研发；不能把旧文件存在或补profile描述为唯一阻塞。
5. 未对HEAD重新执行4751软件全量、浏览器或真实路径；R413为ab18被测基线，R419-R421为42定向P，R422为47定向P/原22目标到原断言，集合不相加、不减法更新35F。
6. docs/current_authoritative_status.md最新页首为11月2快照，R413 11月3长测已给ETEAC/PCSC自然结束与42浏览器P/1skip；其旧19浏览器失败不能列成当前未解决阻塞。
7. 实际后续任务资源余量、磁盘、独占GPU/渲染窗口、raw保存与完整复现交付状态需临运行前检查；本轮不据历史预算开付费或真实动作。

## 最小下一步与停止线

主代理先执行本轮5节点诊断，产出可证伪的事务/握手证据，必要修复另Astra轮。同时可把T7b的“已有校准模块→独立实际来源→冻结应用索引/rolebinding→native_action_contract可信消费者→连续效果证据”与T3b当前角色绑定划为下一研发步骤；先只读核对已有生产者、接口和当前非秘密配置，避免重做已有软件。此处是优先级和准入评估，不授权任意修改模型、资产、阈值或执行真实动作。

只有影响待走入口的未解决来源、owner/lease、回执或安全问题才成为该入口的前置。事件复现、API消费者和UTC性能仍需各自收口；如果实验依赖这些路径，不能跳过其相关验收，但这不要求同时清完全库format/中文治理。UTC历史两后端4502.509秒未达600秒线，保持性能未过；不能把诊断cap延长写成性能通过。

T7b基础几何/运动与连续效果必须在B0和INITIAL之前独立成立，不能等待INITIAL后的T9倒灌，否则形成死循环。T8a离线故障教师不等待T13；T12b边缘模型后置，规则/成本provider按其真实来源验收即可继续核心。全流程保留用户指定Qwen3.8-Max、OpenCV、可见标记、顶视及现控制器；Isaac/G5/腕部相机为可选，不阻塞核心。真实硬件持续NOT_STARTED、S3/S4 LOCKED。

软件、真实采集、真实Max、仿真物理和正式研究分别报告；已分配失败/BLOCKED/未执行全部保留，未知成本为null。完整raw/DB本地保留与精选远端证据包分列。本评估未执行测试、服务、secret或旧DB查询；其完整52项源pin与原始失败见同轮`plan.json`，结构化矩阵见`astra-entry-assessment.json`。
