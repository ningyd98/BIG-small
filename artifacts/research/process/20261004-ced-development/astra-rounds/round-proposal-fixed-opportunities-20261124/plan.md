# 从真实固定候选采集 G3 开发机会

基线004f9c837ce10fea4a3db6097c3f9abb5909d139。原 verified-development/opportunities.json 为空；R07 的 formal_opportunity_producer 明记 NOT_IMPLEMENTED，测试中的构造RGB/深度、模拟命令和 fixture 只描述 schema。v10 LIFT 两个实际准入端点不构成完整固定机会集。已有原生 _candidate、_execution、_label、实际相机三遍读取、原生门控，无须新造正式采集器。工作限独立开发脚本 scripts/graduation/proposal_fixed_opportunities.py、针对缺失证据/篡改/时钟/标签隔离的测试和小型公开清单。实际代码在独立检出运行，现有原件只读。

## 分配

沿用已用开发组 assignment.json 的完整原场景与 seed、资产、320×240、原相机、dt及控制器。开发身份唯一，不加入正式池。两个成对区组，每组同场景同候选分别独立 reset 两次，短/长等待交错，共4个 episode、1种摆放。按物理步预分配 capture 在 settle120，提交等待 (0,96,96,0) 步，约0或0.4s；原机会有效窗0.25s。_candidate(row)原登记目标XY/0.16m、半径0.02m、超时8s；离线分配冻结同一显式指令，所有判定使用同一命令，不从评测时真值修正。相同 seed 不代表4个独立摆放。一次签发一次尝试，不补采。分配前核对输入SHA及当前模块位置、EGL、私有输出、磁盘与独立DB/实例；报告真实wall/模拟时刻，在线时钟与oracle物理年龄分别计，不以软件延时偷换仿真延时。

## 实际采集／盲门控／独立评分

1. 新 CLI allocate / capture / gates / label / score。MuJoCoCaptureSession.apply_scene，reset0起 observe_physics_steps 和 observe_actuator_steps；step120 capture_with_instances 产生真实RGB、光学Z、实例映射和三pass状态哈希，按同一未推进时刻分离出真实 qpos/qvel/act/ctrl 和初始控制参数。只将 RGBD/登记候选与可由机器人公开 API 实测的同帧本体状态交给在线侧。实例ID、真值和未来路径只在oracle侧。登记阶段和实际提交阶段都建绑定，提交时实际校验同一实例、视图、控件计数和当前状态。保留分配身份与原场景哈希，不因复用 assignment_id 合并四个 opportunity_id。
2. 固定普通候选优先经共同 SafetyShield 的正常带目标 PRE、运行时硬安全及 POST（记录真实来源、批准或拒绝原因）。若需用正常 MOVE_ABOVE 安全上下文表达目标，须逐项证明约束、绑定、指令目标、时限、权限与实际执行相同，否则报告共同Shield未证明，不用别的技能名伪装准入。执行原型调用 MuJoCoSkillRobot._move('MOVE_TCP', 实际已登记的Pose, timeout_ms=8000, tcp_velocity=None, acceleration=None) 或同原控制器且真实类型为 MOVE_TCP 的入口。传入用实际状态的硬保护。独立离线参考动作不由受比较的方法准入/拒绝来决定；共同安全拒绝必须停止，保存完整可得前缀。若既有产品安全层无法表示 MOVE_TCP，独立开发物理采集仍可按冻结原 T8a 的隔离离线候选参考环境和其原有物理保护运行，明确两种在线方法共同准入状态为 NOT_ESTABLISHED，单列离线标签实测，绝不把该执行说成经过生产Shield。保留真正 ActionResult、实际半开命令范围、从1开始的完整序号、PRE actuator、全步轨迹直至最后动作，序列与转码沿用 protocol_evidence 源格式。禁止将另一个技能返回的结果改名。
3. 在线回放用原 native_action_contract/真实像素身份生产器、原条件及快照构建同候选，视觉证据缺失填 UNKNOWN、error与motion bound维持None。不存在真正绑定的任务步骤时门级对照记不可评，不设置硬编码 target_visible/PASS，不用测试真值充身份。冻结控制意图中的明确目标可进入两侧；其与当前物体现实的一致性由独立图像/离线证据评估。分别调用真实 validate_b3 / validate_evidence，对同一冻结 UTC/上下文出原始 verdict 和原因并封存；随后独立连接真正oracle与 Opportunity 通过 run_gate_replay 重算，确保 verdict 一致。若方法缺输入，报告缺失与共同安全状态，不能将未调用的方法伪写为已返回 UNKNOWN。无校准证书使 JOINT 拒判是可能结果，TTL沿用真实契约，实测其与oracle时窗是否一致。
4. 离线生成 _label 所要求 capture.json、observation.json、rgb.png、depth.npy、instances.npy、context.json、physical-observations.json、candidate-actions.json、commands.json、actuator-provenance.json。使用归档原 rules，经 _label 实际触发 _trace / _execution；原标签需全部命令区间、一致渲染状态、原摄像机参数、完整碰撞作用域、终点逐轴5mm和包含等待的8s期限。原函数给出的 UNKNOWN 与原因保留。_label 无法处理的采集错误单列，不伪造 VALID 或 INVALID。程序不能通过编造几何公差、吞掉命令、修改原校准或减弱盾产生结果。校验同源快照、丢帧/改SHA、错实际提交步、错目标时不能产出合法标签。只允许用于测试的派生反例，真实四实例分开。

## 输出

逐例报告两种时钟年龄、状态/动作/三pass、真实调度与安全、盲门结果、独立标签。按 oracle VALID/INVALID/UNKNOWN × method VALID/INVALID/UNKNOWN 报计数，另报缺契约/无法执行、共同安全拦截、获准覆盖、无效机会误放行、有効机会误拒绝和两侧拒判率。零分母写null，闭环达不到5mm是oracle UNKNOWN的原因，不能把它算成实际无效机会。对四个预分配逐项留位。报告oracle侧有实测、方法侧是否有可复核完整同源对照以及支持哪些解释；禁止靠全部UNKNOWN取得G3通过。故障/超时封存后按原计划继续不受影响的组，修复新根因另出Astra计划。本轮0商业、0硬件、0正式claim，统计不外推正式200/2400或开题达标。
