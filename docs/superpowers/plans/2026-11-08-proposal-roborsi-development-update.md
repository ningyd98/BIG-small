# 开题三项研究内容与 RoboRSI 借鉴开发方案更新

> **For agentic workers:** 本文件是条件化开发路线图。未来实施沿用 `superpowers:executing-plans` 与适用 Astra 轮次；下列 checkbox 均为待交付事项，不是新的运行额度。已有授权及已冻结执行计划继续按其适用范围执行。

**Goal:** 在开题确定的受控桌面抓放范围内，先取得当前来源的正常闭环与合格基线，再验证观测一致性、风险与成本协同决策、基于效果依赖的有限恢复。

**Architecture:** 云端采用当前用户已选择的精确 `gpt-6.1-sol`；边缘近期使用规则与成本 provider，模型选型后置；端侧保留 OpenCV、RGB-D、可见姿态标记、顶视相机及既定控制器/SafetyShield。RoboRSI 的反馈组织、上下文预算和版本评测思路融入已有模块。

**Tech Stack:** 现有 Python/OpenCV/MuJoCo、Memory/SQLite 仓储、异步执行器与模型接口。近期不新增模型训练、通用智能体框架或执行引擎。

**Spec:** [开题报告原件](../../../output/doc/20261021-proposal-revision/开题报告-2501220176%20宁业栋_修改版.doc)、[10月24日申请表](../../../output/doc/20261024-opening-application/开题申请_含系统架构图_计划至202704.docx)、[原研究设计](../specs/2026-10-04-cloud-edge-device-research-design.md)、[10月22日开发计划](2026-10-22-post-opening-development-plan.md)。本轮依据[实际 Astra 文档计划](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-roborsi-proposal-update-20261108/plan.json)编制。

## 1. 本次更新的效力与当前起点

编制日期为北京时间2026年11月8日；输入 HEAD 为 `ae3b88370276ebe0b2782720588c0b52d6c8e1d8`，具体证据时点与输入 SHA 见[输入清单](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-roborsi-proposal-update-20261108/input-manifest.json)。

本文件补充覆盖10月22日计划中已过时的云模型、开发起点与高层月度安排，以及10月4日设计中的旧云模型名称。旧文件、开题原件和失败记录原样保留。原 G0—G5、B0—B5、数据隔离、统计、INITIAL/METHOD/FINAL 及现行微观执行约束继续有效。本次只是规划交付，没有执行产品修复、测试、API、渲染或物理运行。

上轮调研回答将10月25日暂停记录和旧 Qwen3.8-Max 方案当作当前状态，现予以纠正；这些是历史材料，不能覆盖11月的真实进展。当前源码和运行材料支持的结论如下。

| 层次 | 本次已核查事实 | 仍不能据此宣称 |
|---|---|---|
| 云端身份 | `configs/research/ced_roles.yaml` 为 `gpt-6.1-sol`；R457—R460已有迁移和四个历史 RGB-D 场景真实 API 回放 | 当前新采集场景、物理动作或完整任务已通过 |
| 软件读取 | R465记录六项 reader、134项相邻回归及静态检查通过 | 新的真实采集或正式研究验收通过 |
| 当前教师链 | R468部分采集保留；R470替代采集 full rc1、read rc0，但九组分数及联合界仍为 null，native_authority 为 UNAVAILABLE | reader退出0等于动作资格成立；可以直接扩大批量 |
| 最新步骤报告 | R470报告记录120物理步、367渲染pass、0完成动作，并报告标记不可观测；本轮仅记录该报告，不诊断或修复 | 标记问题已解决；可自行重试第三次采集 |
| 边缘能力 | 当前规则/成本provider，dispatch=false、local_recover_enabled=false、status=NOT_ACCEPTED | 所有联合决策和局部恢复候选已经开放 |

来源：[R460阶段总结](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round460-openai-sol-real-replay-20261108/implementation/phase-summary.md)、[R465阶段总结](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round465-reader-wire-numeric-type-alias-20261108/implementation/phase-summary.md)、[R470终态](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/full-evidence/result.json)、[R470读出](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/readout/diagnostics.json)、[R470步骤报告](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/implementation/step-report.md)。后续新结果以新终态报告为准，不从目录存在、计划发布或进程退出推定完成。

## 2. 开题内容与值得借鉴的机制

开题的系统架构是工程基础，三个研究问题保持不变。采用“在现有模块内补强”的路线：整体迁移 RoboRSI 会扩大接口、数据和验证范围；立即增加27B/VLA训练会偏离近期主线；仅增加文献引用又不足以落实启发。因此本次将借鉴落到现有接口、阶段出口和对照方法中。

| 开题研究内容 | RoboRSI提供的启发 | BIGsmall拟补强内容 | 对照与证据 |
|---|---|---|---|
| 视觉观测与动作条件一致性 | 工具动作后返回反馈，模型根据新观察修正 | 将新观测、三值条件、拒绝原因、版本和已验证效果组织为结构化反馈；云返回与提交前仍由本地规则复核 | 同一固定动作机会对比完整门控与既有B3；报误放行、误拒、UNKNOWN及独立物理结果 |
| 风险与通信成本协同决策 | 监督频率、动作跨度、上下文组织共同影响成本和成功率 | 保留周期/事件对照，先筛合法候选，再比较校准风险与实测成本；明确提示和上下文的共同配置 | B0/B1/B2/本方法同基础能力配对；分别统计请求、tokens、字节、端到端时间、本地资源 |
| 执行反馈与局部修复 | 从失败中修正策略，复用任务经验 | 用失败证据与效果依赖确定受影响后缀；新帧复核保留效果，修复后再次验证 | 与B4完整剩余计划修复比较；同故障输入/预算，记录恢复率、惩罚耗时及不可重复动作重提交 |

外部能力依据见[智能体配置][RSI-agent]、[评测协议][RSI-eval]和[上下文实现][RSI-context]。配套研究§3.1中动作审查跨度4对应成功率23.61%→25.83%、Token下降63.5%；这是该实验的动作粒度结果，不是事件触发策略，也不作为本项目收益承诺。[配套研究][RSI-paper]

### 具体适配边界

1. **结构化反馈优先。** 复用 `vision/supervision.py::SupervisionContext`、`decide_supervision`、`vision/planner.py::RGBDPlannerAdapter` 与 `vision/messages.py::build_visual_messages`。拟增加的反馈内容先核对现有字段和来源，再由限定实施计划定义最小schema差异。不要假定现有接口已经包含全部失败、效果和预算信息。
2. **上下文先固定，再优化。** 提示生成规则和预算属于共同实验基础。保留当前任务/观测绑定、取消与截止条件、未解决失败和必要效果依据；历史摘要标注来源与时效，不充当当前观测。优先采用确定性摘要；如后续使用模型生成摘要，其调用、耗时和费用必须计入。
3. **经验包属于后置扩展。** 仅用隔离开发来源，记录适用条件、观察、动作、结果、未知项和经验证策略，审查后冻结版本与hash。优先少量任务相关经验，不建设跨任务自动检索平台。经验中的坐标不直接执行，必须用当前图像重新定位。[经验包][RSI-package]、[任务记忆][RSI-memory]
4. **执行权继续留在原运行时。** 云模型只产生候选意图，已有SkillExecutor、仓储CAS和SafetyShield拥有提交/执行边界；不另建RoboRSI到机械臂的旁路，不允许模型修改安全规则或自动放宽门槛。
5. **保留在线/离线评价分离。** RoboCasa公开提示会把环境`state.success`提供给智能体；BIGsmall不能照搬该反馈。独立物理成功、教师真值及正式测试标签仅供离线评价，在线完成必须由新帧与允许的本体反馈支持。[RoboCasa提示][RSI-prompt]

## 3. Global Constraints

- 保留可见姿态标记、顶视相机、OpenCV/RGB-D、当前控制器；云模型以现行用户选择与冻结角色为准，边缘模型后置。
- 每个provider在途模型请求上限1；最新待发观测有界合并。云模型不进入实时伺服环；硬停止独立于云端响应。
- 新问题/计划外失败先实际Astra限定计划；保存输入SHA、原始失败、实施和验证证据。现有运行额度、预算、TTL与冻结字节不得因本路线图刷新。
- 在线只消费可观测证据；UNKNOWN不通过教师真值、历史记忆、模型自报置信度或扩大TTL变成PASS。
- 标定、策略选择、基础先导、功效先导和正式测试按来源组隔离，派生帧跟随原组；失败、停止、超时、BLOCKED全部保留分母。
- 请求、用量、账单费用、应用字节和本地资源分别记录，未知费用及纯推理耗时为null；不将RTT当成纯推理耗时。
- 软件验证、实际仿真、真实API、正式研究与实机分别验收；S3/S4与真实硬件不由此开放。

## 4. Review Focus

1. 摘要删掉关键失败或把旧经验当当前事实：工作包3/4覆盖摘要前后身份与拒绝结果、旧坐标不可执行。
2. 主方法独享更好提示/经验：工作包2/4冻结共同配置；经验有无另作独立对照。
3. 延迟注入只延长程序等待，没有环境推进证据：工作包2/3登记物理/墙钟映射及等待模式，检查实际观测年龄和状态变化。
4. reader成功、模型finish或controller ACK被当作任务成功：工作包1/3/5要求新帧效果与独立物理评价，并保留不一致。
5. 局部修复重复不可逆动作或重启刷新预算：工作包5验证效果身份、CAS与原预算，恢复能力不足则升级/停止。

## 5. 分阶段开发与可核验出口

以下仅定位现有模块和后续交付。文件不因出现在表中就获准修改；精确差异、测试节点、命令及实际运行额度由实施时适用的Astra计划冻结。每包均应经历限定软件验证、必要实际运行、独立读出与明确范围验收，不新增统一巨型runner。

### 工作包1：完成当前资格链与第一条正常动作正链

**对应旧任务：** P6剩余项、P7/P8/P6D、现行云角色证据；10月22日Tasks 1—3。R465已接受的软件范围直接复用，不重做已完成迁移。

**Files/Interfaces:** `scripts/probe_rgbd_roles.py`、`research/freeze_evidence.py::verify_role_probe_evidence`、`scripts/collect_native_calibration.py`、`research/native_collection_application.py`、`vision/execution.py`；已有验证定位 `tests/test_sol_evidence_reader.py`、`tests/test_native_action_submit.py`、`tests/test_native_calibration_collection.py`。

- [ ] 核对最新终态与后继Astra计划，区分R470部分采集和R469 nominal计划；本文件不修复标记或读出问题，不重置任何一次性额度。
- [ ] 现行云端nominal与零云教师完整动作资格分别推进；两者不互相要求先PASS，GPU实际阶段按现行锁串行。nominal通过不替代动作资格，教师成功不替代在线模型成功。
- [ ] 保持P6完整顺序 **A→B→C→P7/P8→D**；先完成一个实际完整标定组及独立reader，再按原计划扩展至少九独立支持组，随后完成三处native消费与Memory/SQLite正常正链。
- [ ] 正常开发任务保存“观测→候选→核验→提交→启动→效果”的同一episode记录，保持失败/未知；单例只证明可达，不声明静态成功率达标。

**出口：** 当前来源的完整动作资格、正常动作正链和各自验收记录。未经这些证据，后续策略不因软件接口已存在而开放。

### 工作包2：合格B0与可比较的统一实验入口

**对应旧任务：** T8/P9、10月22日Task 4；继续使用现有pilot、CostLedger及独立审计。

**Files/Interfaces:** `scripts/run_rgbd_pilot.py`、`configs/research/ced_selection.yaml`、`configs/research/ced_foundation.yaml`、`research/protocol_evidence.py`、`research/freeze_evidence.py`、`research/cost_ledger.py::CostLedger`；已有验证定位 `tests/test_ced_pilot_stages.py`、`tests/test_ced_initial_freeze.py`、`tests/test_research_network.py`、`tests/test_research_cost_ledger.py`。

- [ ] 在方法比较前记录模型/角色/有效请求参数、提示生成规则、上下文预算、经验版本、技能/视觉/标定、控制器与安全层；方法ID只对应明确的机制差异。
- [ ] 记录物理时间与墙钟映射、网络日程、推理等待期间环境推进方式。保持既有运行约束；暂停物理的诊断模式单列，不能混入动态主比较。尚无环境推进证据时不宣称已验证动态延迟鲁棒性。
- [ ] 完成固定机会与200组离线可恢复性证明；在120个selection组上配对筛选0.5/1/2/5秒周期，再在另120组做基础先导。无合格者NO_FEASIBLE_BASELINE，预算不足INCOMPLETE。
- [ ] INITIAL前登记三模块消融与旧B3/B4等对照的对应、比较问题及统计规则；完成真实来源与成本核验后再冻结INITIAL。

**出口：** 合格共同B0、完整新基础先导、INITIAL及成功路径资源估算。请求减少必须在合格基线之上评价。

### 工作包3：一致性检查与结构化执行反馈

**对应旧任务：** 一致性研究、T10及P8/P12相关路径；基础执行门控是工作包1/2前置，本包完成研究增强与独立比较，不造成依赖倒置。

**Files/Interfaces:** `vision/messages.py::build_visual_messages`、`vision/supervision.py::SupervisionContext/decide_supervision`、`vision/planner.py::RGBDPlannerAdapter`、`edge/evidence/{conditions,validator}.py`、`vision/action_evidence.py`；已有验证定位 `tests/test_visual_evidence_contract.py`、`tests/test_visual_effect_evidence.py`、`tests/test_visual_supervision.py`。

- [ ] 基于现有来源构造最小反馈：当前目标/任务/计划绑定、条件PASS/FAIL/UNKNOWN及原因、实际效果依据、合法处理方式与剩余预算；对缺失字段保持明确未知，不拼造证据。
- [ ] 在云返回、动作提交前和动作后新帧三个边界核验；覆盖目标移动、旧帧、遮挡、无效深度、标定变化、迟到回复及取消/版本变化。
- [ ] 对摘要与未摘要输入检查关键绑定和拒绝语义，不能靠文字摘要恢复已失效的证据；额外模型摘要如启用须纳入总调用成本。
- [ ] 在既定固定机会上与B3比较误放行/误拒/UNKNOWN；实际正常正例与拒绝反例同时保留，不以全STOP通过替代闭环。

**出口：** 一致性研究的完整判定来源与配对结果；在线效果和独立物理评价不一致时分别报告。

### 工作包4：风险与成本约束下的选择性云端介入

**对应旧任务：** T9/T11/T12、P10/P11/P12及10月22日Task 5。

**Files/Interfaces:** `auto_mode/joint_policy.py::JointEvidencePolicy.decide/estimate_action_costs`、`vision/risk/`、`edge/recovery/verification_router.py::route_verification`；已有验证定位 `tests/test_joint_visual_policy.py`、`tests/test_rgbd_risk_calibration.py`、`tests/test_research_risk_sources.py`。

- [ ] 用独立数据校准风险和选择阈值；规则分数不称概率，缺成本/风险不填伪值。先筛候选资格，再比较代价，不重写第二套路由器。
- [ ] 同场景/seed/网络日程比较B0周期监督、B1固定阈值、B2规则AUTO及本方法，保留相同provider、上下文生成算法/预算、经验版本和安全层。不同触发时刻允许产生不同观测，这是方法差异，不能强行替换为相同旧帧。
- [ ] 完成原P12的8新场景×4方法开发验证，保留合法正链和失效/拒绝场景；LOCAL_RECOVER在工作包5验收前不可选。
- [ ] 请求数、原始usage、字节、端到端等待和本地资源分列；新增记录观测年龄、上下文大小、无进展原因作为诊断观察项，不增加硬门禁。

**出口：** 实际决策链和成本来源可复算；正式收益待FINAL后的配对实验。动作批次长度或27B替换不加入当前主比较。

**可选经验实验：** 基础能力及主方法稳定后，若资源允许，可在同一冻结策略下比较无经验与固定经验包。两组同样记录上下文成本、重观测/云升级及任务结果；经验仅来自开发来源，正式测试不更新包、不跨测试episode写记忆。该实验单独预登记，不阻塞主线、不把经验收益归因给云边触发策略。

### 工作包5：效果依赖与有限局部修复

**对应旧任务：** T13及10月22日Task 6。

**Files/Interfaces:** `cloud/replanning/visual_dependencies.py::find_repair_window`、`cloud/replanning/visual_repair.py::build_visual_repair(full_remaining=...)`、`edge/recovery/lifecycle.py`，复用现有ReplanApplyService与仓储CAS；已有验证定位 `tests/test_visual_local_repair.py`、`tests/test_role_visual_repair.py`、`tests/test_verified_recovery_lifecycle.py`。

- [ ] 以新观测复核已完成效果，沿前置条件/效果依赖定位受影响未完成步骤。现有`RepairWindow`只产生候选，已完成效果不能因为旧证据失效就自动重放。
- [ ] 当前状态不支持保留时，重新识别有独立身份的补偿或升级/停止；恢复后用新帧验证，禁止将授权/ACK/动作返回当作恢复成功。
- [ ] 在同故障与预算下比较局部修复和`full_remaining=True`的B4；覆盖目标移动、抓取失败、放置不合格、重复故障、无进展、重启及预算耗尽。
- [ ] 保持原次数/调用预算与60秒恢复墙钟上限，已完成不可重复动作重提交为0；验收后才开放相应候选。

**出口：** 有限恢复开发能力与适用范围。200组离线可恢复性证明、开发恢复运行、200组正式G4评价分别记录，不互相替代。

### 工作包6：冻结、正式实验与论文交付

- [ ] METHOD冻结共同模型、上下文/经验配置、端侧算法、阈值、预算与消融开关；标定、选择、基础、功效、正式来源互斥。
- [ ] 另120个配对功效组不再调参，按α=0.05、power=0.8及既定校正规则，从每方法N∈{600,1200,1800,2400}确定样本量；资源或功效不满足则保留未完成，不追加至显著。
- [ ] FINAL后按既定三任务层×四网络档位等条件做主对照/消融；保留失败惩罚、场景聚类配对bootstrap≥10000次、95%区间与Holm校正。基础安全层不因消融被删除。
- [ ] 论文按三研究问题组织机制、证据、消融和限制；将RoboRSI列为运行框架/反馈/成本权衡相关工作，不声称本项目已证明通用机器人能力或独有理论创新。

## 6. 保留的研究目标与新观察项

| 项目 | 沿用的目标/验收口径 |
|---|---|
| G1基础能力 | 有效目标定位P90≤10mm，另报覆盖；独立静态抓放≥90%；抓取抬升≥50mm保持≥0.5秒，释放后目标区稳定≥1秒 |
| B0资格 | 静态≥90%、整体≥80%、安全违规≤1%；无合格基线不能宣称请求节省 |
| G2协同 | 云请求均值减少≥30%；成功率差单侧95%下界>−3个百分点；安全违规率差单侧95%上界≤+1个百分点 |
| G2a工程成本 | 应用字节减少≥25%、含失败惩罚任务耗时P95减少≥15%，分别判断；未知账单不估造 |
| G3门控 | 对B3误放行减少≥50%且绝对≤2%；有效安全机会误拒≤5%；UNKNOWN单列 |
| G4恢复 | 200组正式故障恢复成功≥80%；含失败惩罚恢复耗时中位数减少≥30%；不可重复动作重提交0 |
| 可选扩展 | G5及模型训练保留原可选性质；经验包和上下文优化不自动加入核心目标或扩大样本承诺 |

任务失败惩罚继续按旧计划 `Tcap=clip(ceil(P99_B0成功耗时×2/10)×10,120,600)` 秒，恢复失败惩罚 `Rcap=60` 秒。点估计目标与置信区间判断分开。新增上下文大小、经验命中、观测年龄等只作为可解释性观察，不替代上述目标或增加晋级条件。

## 7. 月度安排与最近交付

月度安排参考10月24日“计划至202704”申请表：相较10月21日目录中的报告，本次将2月用于冻结/功效与准备，3月用于正式实验和初稿，4月用于定稿交付。此为开发建议，不声称已获导师批准，不修改开题原件、专业信息或学院答辩日期；所有阶段在满足前置条件后推进。

| 时间目标 | 开发重点 | 可核验交付 |
|---|---|---|
| 2026年11月 | 工作包1—2：当前资格链、完整正常抓放、合格周期基线 | 完整来源正链、独立动作标定、合格B0、新120组与INITIAL；未满足则继续收敛 |
| 2026年12月 | 工作包3—4：一致性、结构化反馈、风险与成本协同 | 正常/拒绝成对证据、开发决策闭环、实测成本和共同输入快照 |
| 2027年1月 | 工作包5：有限恢复及集成 | 局部/完整剩余计划修复对照、效果保护与预算证据、可冻结原型 |
| 2027年2月 | 工作包6前半：METHOD、独立功效、预算、FINAL | 固定方法与消融、正式N、资源预算、可复算协议 |
| 2027年3月 | 工作包6后半：正式配对/消融/恢复实验 | 全分母数据、区间与负结果分析、论文初稿 |
| 2027年4月 | 论文修订、演示及可追溯交付 | 原型、代码配置、研究记录和论文；答辩按学院正式安排 |

最近三项交付以验收顺序为准：①接续最新Astra限定诊断与现行资格链，形成首个完整正常正链；②合格B0与INITIAL；③在共同冻结输入上验证三机制。首项未达标时，不提前扩建经验检索、训练或外部benchmark矩阵。

## 8. 研发与交付方式的收敛

每轮保留实际Astra计划、必要直接输入SHA、原始失败、限定实施与验证、步骤报告和阶段总结；原始证据归档与每次执行的必要依赖清单分别维护。未来计划不默认递归绑定全部祖先报告，不把整理历史资料设为每个产品里程碑的前置；已冻结约束如需调整，必须在下一适用计划中明确，不能临时绕过。

优先复用现有工具、报告结构和测试夹具。每一交付对应可观察行为，避免用门禁数量、报告数量或累计通过测试数衡量研究进展。只运行适用计划要求及新增问题所需检查，不无理由重复已通过验证。

本轮只新增路线图及精简来源/步骤报告；按六个明确路径提交研发分支，推送后核对本地、上游和远端SHA。完整raw、运行数据库、凭据、权重及SDK仍依原边界管理；本轮小型文档与清单不是完整远端复现包。未来真实运行须复核最新适用计划、当前源码/协议/角色、资源准入和清理/独立读出条件，本文件不替代既有运行授权。

[RSI-agent]: https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/e17ddeebc0ac8b0abc1559032657607a7c67504e/docs/agents.zh-CN.md
[RSI-eval]: https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/e17ddeebc0ac8b0abc1559032657607a7c67504e/docs/evaluation.zh-CN.md
[RSI-context]: https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/e17ddeebc0ac8b0abc1559032657607a7c67504e/roborsi/runtime/context_engine.py
[RSI-package]: https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/e17ddeebc0ac8b0abc1559032657607a7c67504e/roborsi/agents/context_package.py
[RSI-memory]: https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/e17ddeebc0ac8b0abc1559032657607a7c67504e/robots/robocasa/model_eval_agent.py
[RSI-prompt]: https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/e17ddeebc0ac8b0abc1559032657607a7c67504e/configs/agents/robocasa365/target50_prompt.md
[RSI-paper]: https://arxiv.org/html/2610.22471v1
