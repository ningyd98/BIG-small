# 原生开发动作的共同安全层与盲门控比较

基线4bd4deb0716b82e6036b617bb78436390a0e8c12。四个已封存固定MOVE_TCP 物理机会均到达同一目标；0/96/96/0步等待使T8a oracle结果2 VALID、2 INVALID。现存共同方法调用各0。Plan.json绑定四例原始online index/各侧密封及输出，另绑定E八个真正 MOVE_ABOVE 提交的原始帧、完整contract/binding/Shield和时钟，而非关联run的汇总成功值。

## G3 技术判定

TaskStep/SkillName、SafetyContextBuilder、rules中运动及带目标规则、实际executor映射分别核对。MOVE_TCP缺少注册技能和两类适用规则；硬件接口只执行注册技能。MOVE_ABOVE含物体、预置姿态和已绑定grounding约束。即便一次轨迹目标坐标重合也不能证明两种指令端到端语义相同。原native_action_contract给定0.01m容差、5s ordinary TTL、证书None；T8a固定候选的0.02m/8s与oracle 0.25仿真秒有效期是独立定义。禁止把其中一个常数覆写成另一个、改技能名、构造绕验证对象、复制部分Shield规则作为共同层。一个只读候选类型可为未来设计，只有原规则所有按技能适用性、全契约、证据与时钟语义、受限执行映射明确冻结并独立验收后，才能声称同一安全层。在现阶段没有可证明的注册等价关系，不扩展执行集合。此前四个标签保持独立，G3误放行/拒绝不可估计。以后若要把MOVE_TCP纳入共同方法，需要用户确定是否新建协议版本、批准语义映射/研究评审与重新分配独立样本；本计划不需要这项决定即可执行。

## 真实 MOVE_ABOVE 盲工程对照

独立新脚本 proposal_development_gate_binding.py allocate/extract/gates/score，全部只读，不执行任何动作。预分配E四个已冻结摆放×名义/平移，每个episode只取首次已实际提交的MOVE_ABOVE PRE，共8事件，独立摆放4。冻出完整列表、预计源SHA、实际指令/目标和提取规则，禁止按前置成功或时间有效性再筛。用 run.json frame_roles 对齐 PRE_conditions、PRE_Shield、dispatch_source_recheck 与实际dispatch、首条真实命令；同一绑定、episode、frame ID/checksum、实际evaluated_rules、无修改、真实时刻先后和原有效期均逐项读回。保留当时正常 SafetyShield.pre_check 原始决策与完整规则记录；它是当时真实调用，本轮不得把简化context重跑写成第二次真实准入。

唯一主分析是重放历史 PRE 条件检查快照：取该原帧、审计中PRE的真实RobotState、grounded_step与executed_contract，核实original.digest()真正来源、版本、command_seq，按动态入口原逻辑 bootstrap_collection_tracker(handoff,geometry) 后调用 self.color.facts(PRE,state) 重建首动作同帧事实。对该首动作，guarded_clock 在handoff重建tracker，首次PRE复用同一 stage_source；必须从真实 handoff 帧恢复引用同一对象的历史行文，不通过临时生成便利观测。小心 grounding audit 的 online.visual_facts={} 是准备输入，不代表 PRE 条件输入。冻结事实重建并标明可重算来源；历史输入无法证明时，允许单列直接用其真实已封存空事实的“准备阶段”盲判，不能代替提交时刻PRE或补造身份。以实际 pre-dispatch 最后一次 dispatch_source_recheck.checked_at 为两个方法共同的replay_now，并单列PRE_Shield时刻、采图年龄、binding.valid_until；仅存在明确事件才可使用。按原代码 native_action_contract(snapshot,executed_contract,grounded_step) 构造一次，调用真实 validate_b3 / validate_evidence，完全同源同now、相同普通TTL。原 ground step 空preconditions如实保留，另记录真实注册动作 PRE 独立检验各项，禁止删改事实、填calibration bounds或把PRE通过盖成CONFIRMED。原合法动作保留其自己的参数和时钟。对预先指定的8个阶段分别计输入缺失、不调用、VALID/INVALID/UNKNOWN和具体原因；不因TTL超限修改时钟。盲工作进程只接收选定的真实PRE材料与历史Shield/时间，隔离 oracle、结果、下游sim真值；从混合run和audit归档以白名单提取，输出SHA证明。读回重新比对规则/绑定/两方法返回值。负控针对调包、错step或错误时间、以grounding空事实冒充PRE、错标签拼接。用既定相机和控制方法的独立读回可核查实际到达阶段，但不能用历史整任务失败、20mm目标误差或另一项目的4个标签充作MOVE_ABOVE oracle。

## 若缺失当时PRE事实的直接记录

若盲重建失败或无法认定原PRE来源，仅对缺失的采集环节用同一个开发入口补至多两次当代真正MOVE_ABOVE提交：在E已用t01位置、名义/平移各一次，独立episode，预登记并保持原安全/控制条件。让原worker/Shield执行正常PRE与提交，用只读旁路从调用处捕获实际同一OnlineEvidenceSnapshot、TaskContract/step、now、完整实际SafetyContext与原决策、实际命令/关联角色，向两个原方法各送一份相同冻结输入。仅观测，不用任何新方法判定操控或越过Shield；拒绝的事件仍登记。旁路可在独立开发runner使用显式可选记录器，无须修改产品类型、规则或授权。真实增量事件与历史8例分列，不能将新事实追认旧动作。若历史8条可复算则无需额外派发。保留无误差/运动证书为None的原结果，报告调用覆盖、共同Shield覆盖、真实两方法判定及年龄、逐机会差异；无对应独立物理oracle时报误放行/误拒率null。只允许本地开发读回和必要的两个MuJoCo实例，不动原四机会、v9/v10、商业云或实机。新根因保留原件另轮计划。
