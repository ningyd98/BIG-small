# P2 动作参考与双时间域合同

软件合同可行性冻结；actual=0，校准值未建立，native/formal资格未验收。NativeActionTiming是frozen描述数据，不能签发来源、窗口或资格。原resolve_native_reference签名、UTC estimate/注册schema、10mm及原消费者guard保持。

S由同backend/episode物理模拟时间提供：a_S=current_sim_s-capture_sim_s，H_S为完整nominal动作horizon（max原/编译timeout与expected_duration，再保留更长真实owner horizon），不缩为早成功时长。误差描述为 e_m+v_ref[m/SimulationS-second]*(a_S+H_S)。e必须由独立完整geometry/tracking/holding支持，v是参考漂移而非body/TCP主动速度。0.005sim秒采样gap与端点位移/时长均不证明连续速度。

D由实际OC1来源及适用suspend语义负责整数ns TTL/deadline：普通/condition 5秒、接收5000ms、future规则1000ms保留；D deadline等值拒绝的现有逻辑保持。P2纯诊断只比较描述age<=5_000_000_000（题定TTL5秒允许，+1ns超限），不读取live D、不传caller-now给窗口、不刷新预算。完整未来H_D不能由sim timeout、过去均值、resolution或历史A/B推得。

|动作|参考|几何/执行误差量 e（原定义保持）|参考运动量|完整S horizon|future D|生产者/支持缺项|状态|
|---|---|---|---|---|---|---|---|
|LIFT|精确编译FIXED_WORLD_TCP_GOAL|原joint full rigid geometry、source-derived goal、完整H终态tracking最大误差；独立lift/holding量仍需|完整payload/source重建后坐标0，body移动不为0|上述max+owner；抬升≥50mm、保持≥0.5sim秒独立|若动作资格要求full future必须实际来源|resolver/registry endpoint已可重建；原raw producer离线终态量；operational认证/完整futureD/支持组尚未建立|固定reference数学可达；当前native UNKNOWN|
|RETREAT|精确编译FIXED_WORLD_TCP_GOAL|同上geometry+goal+terminal tracking，原安全条件独立|同上坐标0|上述完整H|同上|同上；绝不以return/timeout替代H|当前native UNKNOWN|
|MOVE_TO_REGION|精确编译FIXED_WORLD_TCP_GOAL|原joint geometry/goal/terminal tracking；holding稳定独立|坐标0；主动搬运非reference drift|上述完整H|同上|同上，真实携带/holding界仍需独立来源|当前native UNKNOWN|
|PLACE|精确编译FIXED_WORLD_TCP_GOAL|原joint geometry/goal/terminal tracking；释放后的区域稳定不是endpoint界|坐标0|上述完整H；释放后≥1sim秒稳定独立|同上|同上，放置/holding/释放条件不能由0参考速度替代|当前native UNKNOWN|
|MOVE_ABOVE|OBJECT_CONTACT|原object全范围/接触TCP geometry+terminal quantity，不换量定义|mutable目标未来漂移源缺失，None|上述完整H|完整future D缺真实来源|现有marker/geometry/raw可离线重建；无连续future reference-motion生产者|NOT_SUPPORTED / UNKNOWN|
|APPROACH|OBJECT_CONTACT|同上|None，不能用固定payload flag改标reference|上述完整H|同上|同上|NOT_SUPPORTED / UNKNOWN|
|GRASP|OBJECT_CONTACT|原contact/geometry量；不暗中把target drift藏入e|None，不能有限/0|上述完整H，闭合/接触/holding规则独立|同上|mutable contact及full future D均无真实支持路径|NOT_SUPPORTED / UNKNOWN|
|RELEASE/HOME/OBSERVE/LOCATE_OBJECT/VERIFY_RESULT/SAFE_STOP|不在现有resolver支持域|各自原condition/hard-stop独立，不能从本合同继承geometry界|UNKNOWN|各自原owner定义，未在P2新增支持|UNKNOWN|不扩本次reference allowlist；hard-stop保持独立|NOT_SUPPORTED|

三消费者为 vision/action_evidence.py、auto_mode/runtime_composition.py、auto_mode/joint_policy.py，本次只冻结共同语义，不接入/修改这些消费者。未来P7/P8需由registered native calibration producer与真实worker/current-owner reader提供不可复制认证来源，绑定同backend/episode、完整S horizon与独立D窗口。public Mapping、哈希、bool、finite scalar、software fixture或teacher真值不能授资格。

固定参考的可达性只在数学合同层：完整source证明endpoint恒定时v_ref=0，独立e=.004m可在10mm内，即使body要移动.12m或更远；未取得真实e/holding/未来来源，不能宣称动作SUPPORTED。命名S/D例a_S=2、H_S=3、v=.001、e=.004得到.009m；D age改变不改变S乘法。NativeTimingCalculation始终native_completion_bound_m=None、full_future_qualification=UNKNOWN、native_authority=UNAVAILABLE；finite future_wall_bound_ns也只是声明。

已有transport两端点原件证据作为旧回归：lift87.8292524mm/2.8958333565sim秒，搬运345.2214690mm/5.0208333735sim秒；总body速度用于原门会使完整动作界>0.30m，不能过10mm。未新增物理实验来复证。改变成reference坐标量只避免混淆，不消除真实tracking/holding要求。

可行性停点：GRASP/mutable contact与完整future D缺真实源，停止依赖该完整抓放动作的九组/大先导批量。不能靠加样本修来源缺项；任何吸收target drift的全horizon contact-completion新量须另写版本化设计交ROOT/实际Astra，本任务不实施。coverage0.9、至少9独立支持组件、所有失败/UNKNOWN/infinity分母原样，P2未收新组。
