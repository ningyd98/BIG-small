# Astra：独立UTC是否为原研究硬依赖的限定审计

**结论：建议合法修订后续工程计划，增加明确版本的单应用仿真 operational-clock 路径；不建议把外部 calibrated UTC 当所有仿真实证工作的必经门。** 原研究要求可审的时效、绝对截止、墙钟预算、统一运行时钟和墙钟—仿真映射，没有发现“必须独立校准UTC”这一硬要求。当前UTC必要性主要来自后来native source/原件重建的具体工程合同，不能由此反推原研究必须依赖外部授时。

这不是现有路径的豁免。现有严格UTC工厂、旧RawV3读取器、冻结结果和guard必须保持；新增域必须以新schema/source factory、真实app-owned事件和完整消费者迁移独立验收。数学上可在同一真实操作计数域内给出保守的**历史年龄、当前读数、截止比较**，无需知道UTC偏差；但不能因此获得SI计量准确度、任意跨机时钟比较、未来执行耗时界、连续运动界或真实机器人准入。校准组、G1、0.005模拟gap、0.01m、coverage .9、TTL、deadline和统计门均不变。

本次仅只读设计审计，新增本报告及JSON；0软件测试、0actual、0代码/原计划/Stage/Git修改。模型为用户指定的Astra；未做运行时模型元数据探测。R3当前开发与受审prefix仍继续，本审计不暂停或改向其实施；新标记及R7真实离线来源继续独立推进。

## 1. 源头合同与后加实现分开判定

| 证据位置 | 实际要求/实现 | 本审计解释 |
| --- | --- | --- |
| `docs/superpowers/specs/2026-10-03-rgbd-evidence-research-design.md:27` B2 | 相同运行中决策入口、时钟、安全边界 | 必须同一测量与调度语义，不指定UTC或外部精度源 |
| 同文件 §4.3（:80） | 几何界＋运动界×（观测年龄＋预计动作持续时间）≤允许误差，未知则UNKNOWN | 年龄、速度、持续时间必须同域同单位；没有允许忽略运动/几何界 |
| 同文件 §4.4–4.5（:92、:102） | created/valid_until、提交前复核；墙钟时间预算；重启保留剩余与绝对截止 | 必须覆盖全部决策生命周期与重启；“绝对截止”可为固定域中的绝对刻度，但不能收到回复或重启后重新起算 |
| 同文件 §5.1、§5.4（:120、:142）及20261004设计:121 | 可解释墙钟/仿真映射；请求等待期间物理继续；耗时含端到端确认 | 不能把仿真秒当墙钟秒，不要求UTC epoch精度 |
| 继承的 `2026-10-03-rgbd-mujoco-dataset-design.md:23` | 在线接收超过5000ms或超前服务器超过1000ms拒绝；离线不得改时间戳伪装实时 | 新域仍必须执行5000ms接收年龄和1000ms未来异常规则；外部输入不能凭单机模式免检 |
| `research/native_geometry_calibration.py:189,289,495` | 独立UTC bracket原件；预注册UTC早于原动作/采集；RawV3 UTC BRACKETED且声明覆盖实测 | 这是当前native v1的硬实现前提；不能直接删掉这些if或给None填0 |
| `research/raw_episode_v3.py:456,1045` | monotonic/UTC pair、descriptor；用UTC offset交集及uncertainty判映射；UTC跳变可影响读取结果 | 原件已有用于操作排序的monotonic bracket，但旧reader不是新域证书；新版本不能追改旧v1/v3判定 |
| `vision/action_evidence.py:17–49` | 三入口调用的 `native_action_contract` 当前仍给geometry/motion bounds=None | 当前消费者不是“已有有限证书只缺一个clock flag”；新source与真实几何/动作支持仍须接入 |
| `edge/evidence/validator.py:58,76,127,180`、`conditions.py:130` | datetime年龄、5秒普通TTL/condition默认max-age、age＋duration、created/valid_until | 仅native factory迁移不足；下游仍在datetime域比较 |
| `simulation/mujoco/motion_controller.py:98` 与 `research/native_geometry_calibration.py:651` | timeout转最大sim步数；完整终态按start_sim+horizon寻找 | 动作horizon当前是仿真量；不应未经映射与wall age混加 |

此外，`vision/supervision.py:59`、`marker_association.py:446`、`worker_runtime.py:422,502,857,933–969`、`repositories/event_autonomy/visual_verification.py:770–785,1013`、SQLite job lease及owner窗口都使用datetime。`vision/execution.py:582–594`已有monotonic deadline，但用datetime差重建原task起点；:1721周期游标仍由UTC差计算。现状是混合实现，不能宣称“全部已经monotonic”。

检索范围包括两份原研究spec及其继承的direct-input/mujoco-dataset设计；结论限这些已查项目合同，不代表外部安全标准、未来硬件合同或所有第三方接口没有UTC要求。

## 2. R02/R03能证明什么，缺什么

Stage55记录R01完整4807采集/4618 OBSERVED/189 UNKNOWN，采集wall 915.764513714秒，最大sim采样gap约0.0041666667秒；这已经说明逐步采样成本与模拟时间不可等同。单组640×480/noise0、自定义source，仍不成为默认域或独立校准组。

R02经过pin补修的20项是SOFTWARE_ONLY。真实Go验签fixture给6秒条件UTC区间，超过默认5秒TTL；它不是实际服务性能测量。issuer accuracy仍UNVERIFIED。R03 root实现审查明确：A/B包围的是B发送前历史slab，B验证以后任何新current-time没有可外推的UTC上界。分小slab只能讨论历史包围宽度；**没有独立rate/current-time依据时，它不能自动修好在线now。** 之前计划将首prefix宽度作为consumer可行性门，现应限定为必要宽度诊断，不称充分可行性。

外部UTC路线并非逻辑上错误。如果任务确实要对独立UTC deadline决策，就需要在该决策/事件时刻有支持的当前区间、issuer/转换/准确性依据；历史A/B、签名、NTP标志、host datetime、resolution、任意ppm都不够。缺口是相应时刻与scope的真实source证据，并不能由此直接断定必须购买GNSS。可用来源要逐项证明其精度/覆盖/时标/当前读数/执行绑定；本任务未调查或推荐购买硬件。

## 3. 一个可审的替代数学合同

建议名称为 **`simulation.operational-time.v1`**（仅提案，尚未实现）。其权威量不是UTC，而是实际应用域D内受支持的单调计数读数C，单位明确为“操作计数秒：10^9计数单位”。所有比较基于同一个冻结API/实现、epoch、应用/worker/lease来源，不能把任意JSON中的数值宣称为D。

### 3.1 前提与范围

1. 实际事件在同一counter域内；counter有已核对的非递减语义，读数通过实际owner在事件前后采样。这里假设的是所选实现的序关系契约，不是与SI/UTC的频率准确度。`get_clock_info().resolution`只登记描述，既不是±误差也不是accuracy；不得据它加一个“精度padding”然后称SI可信。
2. 事件括号来自同一真实控制流：已登记capture/RESET/dispatch/transaction/完成事件及原始读数。异步相机或cached frame的时间必须指向真实原sensor acquisition；读取缓存的时间不能替换采集时间。单个 `_clock_pair()` 包围datetime调用，不自动包围整个曝光/模型请求/物理动作，须用真实operation BEGIN/END及source join。
3. domain绑定app启动/计数实现/进程与owner epoch及原始lease；不得只用PID或调用方domain字符串。并发callback先后/日志seq不等于实际事件全序，允许合法重叠interval，必须由原始因果边界给序。
4. 来源须说明suspend/resume和重启语义。若counter在suspend期间不计时，不能把休眠从原墙钟预算中扣掉。使用有可核对来源的包含suspend的同域计数服务，或者在恢复后凭真实lifecycle证据终止旧域；单凭counter未倒退无法侦测被忽略的休眠。缺这一证明不得验收完整wall预算路径。
5. scope是可信、固定程序在单机仿真中的运行计数与证据可审性，不是恶意管理员/修改kernel/虚拟时钟对手下的防伪计时。hash和readonly文件不是外部时间见证。若研究要求该更强威胁模型，此替代不成立。

### 3.2 保守年龄与截止

事件e有真实括号 `I_D(e)=[c_minus,c_plus]`，当前消费点有 `I_D(n)=[n_minus,n_plus]`，则同域操作年龄被包围于：

`age_D(e,n) ∈ [max(0,n_minus-c_plus), n_plus-c_minus] / 10^9`。

仅在capture确已先于消费的原始因果证据成立时使用max(0,...)；未来/逆序/缺关联先拒绝，不能用clamp隐藏错误。用上端作TTL检查；5秒等值仍按原`age > 5`拒绝边界，condition同理。对created/valid_until半开区间，要求已确认issued发生，并以 `n_plus < deadline_D` 接受，等值拒绝。1000ms未来规则对新同域输入以完整时间区间保守检查；一个已证明本地capture-before-receive的源应天然非未来，未同域外部时间戳仍走原严格路由或UNKNOWN，不猜offset。

任务真实起点括号为 `[b_minus,b_plus]`，冻结预算T，则可用保守绝对截止 `d_D=b_minus+T*10^9`（相对真实起点不延长T）。Tcap/Rcap、lease、verification budget各自保留原起点和原数值；聚合截止是这些已来源绑定deadline的最小值。重观测、新event_id、模型回复或重启不能重置d_D。整数运算与边界舍入只能向拒绝方向，不能通过浮点截断延后到期。

consumer在事务及真正dispatch前各读一次当前D，不能把排队前的now带到动作入口。这证明的是相应检查点的比较；不凭一次read声称任意阻塞之后的动作仍在期限内。无法有界的阻塞、过期后才返回的动作须实际超时/失败保留；不将OS调度/步进最长延迟伪装成零。

### 3.3 必须拆开的未来horizon与双域

同时保留S：实际backend/episode中的仿真时间/physics step。0.005s最大采样gap、50mm/.5s保持和1s放置稳定均沿原simulation物理定义；不改成host计时。TTL、云请求端到端、PCSC .5/1/2/5周期、任务/恢复wall预算用D。记录每段完整 `(D_BEGIN,D_END,S_BEGIN,S_END,kind,step,owner)`，区分WAIT、controller、renderer和无物理推进时段。

已有 `ExperimentClock` 只把请求等待的D时长转换成要推进的sim步；其mapping不是所有主动动作全局S=D的证明。CPU阻塞、render成本和catch-up形成实际piecewise轨迹。不能从已观测局部平均斜率/割线推断未来S/D上界；不能把sim m/s乘D年龄，或把D m/s乘sim horizon。

原充分条件须在一个物理运动支持域中重新一致表达，例如：

- 若校准给出 `v_S`（米/模拟秒），使用同backend真实capture与current S的保守差 `age_S`，并用认证的完整 `H_S`：`E + v_S*(age_S+H_S) <= 0.01m`；另独立执行原5秒D TTL和所有D deadlines。未来等待/排队的sim推进必须包含在实际登记horizon范围内，不能只算controller步数。
- 若使用 `v_D`，须有原独立校准对同一D、同一调度/仿真策略的实际支持，并且 `H_D` 来自可支撑的完整动作合同；过去采样割线不能充当上界。更改时钟类型/映射/调度适用域后不能复用旧v_D证书。
- 当前native全horizon endpoint经验误差量与运动supremum不同。可保留精确owner/参考/完整S horizon的原经验终态定义，但不能标成连续速度或未来稳定性；coverage .9与所有缺组分母仍适用。

**保守历史年龄不自动给未来耗时界。** `now_plus+H_D<=deadline_D`只有在H_D确是对应完整执行的支持界时，才是整个未来窗口的充分检查；max(timeout_ms,expected_duration_ms)目前还被controller解释成sim步预算，不能直接用作H_D。若只有计划/经验预计时长，必须标该条件假设，并依既有deadline在每个允许的真实effect边界重新检查；不能宣称硬期限内完成已获证明。若现有native准入合同强制完整未来D窗口，而没有对应支持H_D，则新域也必须UNKNOWN，此审计不建议改低该门。独立UTC同样不能凭授时本身补出H_D。

## 4. 全部窗口能否一致迁移

**本地拥有的窗口可以版本化一致迁移；外部绝对UTC窗口不能自动迁移。** 最小迁移闭包如下，少任一项都不是完成：

| 来源/消费者 | 必须做的新版本绑定 | 不允许的捷径 |
| --- | --- | --- |
| 预注册→job→RESET→采集→动作 | 实际应用先持久化固定组清单/source/policy/recipe，再产生sealed prereg事件，后续RESET/采集引用其不可变ID和真实因果链；各组自己的D内证明先后 | 用新填写的preregistered_at或hash排序冒充先发生；不同组域直接比较counter大小 |
| 相机、ordinary capture、marker、condition | 真正acquisition事件ID/bracket、同S snapshot、所有5秒max-age统一D | 新包装旧帧或只改一处validator；给未同步外部图像新domain |
| 三native入口与source/calibration | 新scope/schema，由真实factory产生；时钟、geometry/reference/full horizon分别验证；保留UTC UNKNOWN | `utc_uncertainty_ns=0`、改BRACKETED、给old native字段换同名counter、caller VALID |
| 云发送/返回、监督、局部重规划 | local request ID绑定capture/发送/返回/提交D事件，expires_D在原发送/签发起点确定并clamp task/observation/owner预算；晚回包不延长 | 从回复到达时重新起TTL；相信模型生成UTC时间 |
| original plan/grounding/binding/accept/ACK/start/effect | 所有created/valid_until、执行receipt及repository事务时间使用同版本窗口，并在dispatch再检查；身份/lease/CAS/取消照旧 | datetime旧窗口加一个新now、让ACK自动证明start/effect |
| PCSC/请求等待/预算/账本 | 同一D起点、周期游标、包含排队的请求截止；墙钟耗时/惩罚Tcap/Rcap保持；S独立 | 完整动作结束才tick；只算API推理；将simulation seconds作G2a成本 |
| SQLite lease、heartbeat、publication guard | 新scope的expiry由同一实际clock authority在事务读取，仍核实唯一lease与fencing/attempt；新旧worker不可混域授权 | owner局部D有效但DB旧UTC lease已重分配；移除现有lease检查 |
| restart/suspend | 持久化原deadline/domain/起点/余量与fencing，不续期补时；下面的scope规则 | 新进程monotonic从零或只比较相似数值、忽略离线/休眠时间 |

当前Max adapter在 `vision/planner.py:577–583`输出声明的clock占位符，本地 `visual_bootstrap.py:765`签发合同；其监督响应模型只返回身份/建议，没有可信服务器时间。因此可在新的本地签发路径对这些窗口绑定D，同时保留名义UTC供展示/原件，而不以云端授时为前提。**这不普遍适用于所有TaskContract：** 实际非空UTC有效期、第三方签发绝对日历截止、跨机command lease、JWT/证书等外部协议要求必须继续按其原语义验证；无法证明UTC→D转换则该来源不支持新域，不能覆盖或删除原时间字段。

同进程初始slice只能证明无重启支持范围。原§4.5明确要求重启后预算不延长：若新进程能够通过受支持的同boot/counter authority与持久ledger证明仍是同一连续D，可继承原绝对d_D与fencing；要有真实重启原件。若domain发生变化/不可比较，终止原attempt并保留剩余/原deadline及未完成分母，不重置执行。这是安全回退，**不等于已完成可恢复重启功能验收**。跨boot恢复没有可靠桥接源时不准恢复旧预算；需要哪种桥接证据由该需求决定，不预设必须GNSS。

现有UTC守卫可在过渡期间作为附加veto保留，导致更保守拒绝须报告；不能把它们的UTC判断包装成新域真实性。完整新版本启用必须让上述闭包统一，旧路径/旧输入依旧原判定。新counter采用者不能旁路不认识新domain的外部多worker写入者。

## 5. 何时此替代根本不成立

- 要求对真实SI秒、UTC绝对日历期限、独立外部传感器/执行器时钟或机器人物理安全时间作保证，而没有域间转换、精度/漂移/当前读数证据。
- 任一真实关键事件没有同域来源括号/确切acquisition身份；counter冻结、倒退、epoch变化、跨namespace或suspend缺口无法解释；单纯resolution、NTP同步、caller flag不能修补。
- 部分消费者仍按datetime而另一些按D，并把混合结果宣称新source整体VALID；有未纳入clock authority的并行worker/lease issuer。
- 任务强制完整future D窗口，但只有sim timeout/经验均值/历史clock slab，缺实际支持H_D；或者把sampled endpoint当连续路径界。
- 通过把任务秒重新定义成更慢的计数单位改变原预算公平性。新域必须使用冻结运行平台实际操作计数的既有秒刻度和相同方法配置，禁止调时速、省略等待/休眠或事后选时钟来过5秒/Tcap门。该刻度不声称SI校准。
- 研究协议/实际用户约定或已冻结INITIAL/FINAL明确指定UTC或校准SI量且不允许该scope变更。现尚无accepted INITIAL/FINAL，有空间前置修订；有冻结时只能另立协议代次，不覆盖原件。

## 6. 必要原件和独立反例：只验证这项替代的差异

真实positive最少需要一次新schema、实际startup/repo/lease来源下的预注册→RESET→原SETTLE→真正capture→local now→一次完整受审动作/效果路径；完整组与source再按原R4/R5规则开展，不能用prefix或CPU fixture算校准组。保存counter实现/epoch、prereg持久顺序、事件前后读数、同S step/state、完整failure/attempt分母、三个consumer每次read/判定/dispatch关联，以及所有source/hash和名义UTC UNKNOWN。先取得有限源正分支，再按原规则至少9独立支持组；新clock版本不修好189 UNKNOWN或几何范围缺口。

需要真实模型请求时，保存真实capture/send/response/return/submit事件、payload/source及late回包拒绝；来源还不可用时模型相关验收保持BLOCKED，不能CPU过关关闭Max。完整wall/sim映射须涵盖等待、渲染与动作，真实restart/suspend若支持必须单列原件。任何读取已有R01旧数据只能做诊断，不能retrofit为新source的实际发生证据。

独立CPU反例应通过真正新域reader/工厂/三消费者，不mock其最终verdict：

1. 外来域、PID复用、copied handle、source/lease漂移、换boot或缺pair均拒绝；同一D合法重叠interval不因seq简化误拒。
2. bracket宽度跨过5秒上端、精确5秒与5秒+1ns边界、deadline等值、未来capture>1秒、乱序capture/receipt；不能用midpoint/clamp过门。
3. 只平移/跳变诊断UTC但D/S原件不变，**新域的时间数学**结果不变、UTC仍UNKNOWN；旧UTC路由按原规则拒绝/不可用，实际legacy附加veto不得隐藏。
4. 软件counter加倍/停止、任意resolution/ppm声明不产生SI证书；相同C读数无法识别休眠的控制必须使缺suspend证据的模式不受支持。
5. 发送后排队/迟回包/重观测/新event/restart不刷新原d_D；一次5秒窗口在4.9秒返回但5.1秒dispatch时必须拒绝；ACK不证明start。
6. local placeholder签发路径可生成D窗口；非空外部UTC deadline不能被本地D覆盖；仍属于原域的远端图片必须拒绝或UNKNOWN。
7. 两条不同S/D斜率轨迹不能混用单位；active sim快速推进与render慢推进都要产生不同age_S/age_D；未支持future H_D、漏等待S推进、截短完整H_S均不能finite准入。
8. 9组中共享component/一组UNKNOWN仍按原coverage .9分位和全分母拒绝有限界；改时钟不能改变几何/运动/source完整性。

这些是待实施验证要求，本审计未运行任何测试，没有将合成clock序列视为source正分支。

## 7. 唯一补充执行建议（有向四步，不重启整套研发）

1. **冻结新域合同与最小reader数学。** 在新设计代次明确D/S单位、suspend/restart范围、request/lease/consumer窗口闭包；新增小型 `research/operational_time.py` 与独立CPU测试，类型建议 `OperationalDomain`、`OperationalBracket`、`OperationalDeadline`，不复用datetime类型假装UTC。原件producer字段和读取器先一致，落实上述边界反例。source选择必须应用startup-owned，不能公开flag授权。验收只限SOFTWARE，旧v1/R02/R03仍原语义。
2. **真实RESET/capture/app来源与pre-registration顺序。** 复用R3独审通过的single-recorder/live-handle/原RESET tee部分，在新scope producer/reader接同域时间；来源实现文件以R3最终quiet版本为基线，当前活动模块不先冻结成accepted。R3原有A/B prefix按原任务继续，结果另记；新D路径不等待校准UTC。第一次新actual只验证真实来源与时域，不必先完成九组或Max。无adopted owner仍不能伪造任务原件。
3. **完成窗口闭包与双域动作source，再三消费者/G1。** 精确涉及 `vision/{action_evidence,execution,supervision,worker_runtime,worker_owner,owner_registration,marker_association}.py`、`edge/evidence/{models,validator,conditions}.py`、`repositories/event_autonomy/{visual_bootstrap,visual_supervision,visual_owner,visual_verification}.py`、`edge/recovery/verification_router.py`、`simulation_runtime/{worker,sqlite_repository}.py`、`research/{clock,native_geometry_calibration}.py`、`vision/native_calibration.py`。先做单新schema端到端CPU一条真实接口正负链，再限定actual闭环；涉及源改变只回归上述时间依赖和原有效果/预算控制，不全仓重测。完整horizon/未来D支持缺口仍UNKNOWN。之后R4独立组与R5三消费者保持原门。
4. **进入共同研究协议。** 共同主方法/B0–B5使用同一冻结域和映射；刷新Tcap成本与真实预算，明确结果为单机仿真operational秒、非SI计量保证。R6配置/Max、R7教师与标记修复并行继续；合格B0→INITIAL→风险/恢复/METHOD→功效/FINAL顺序不变。新域首次验收前不宣称R4/R5、UTC、G1或正式研究完成。root按原约定汇总与Git，本审计不执行这些写入。

本建议修订的是工程依赖图：把“外部独立UTC”从所有单机仿真实证的唯一前置，改成“UTC严格路径或经独立验收的新operational仿真路径”。它不是把旧source UNKNOWN改为VALID，也不承诺新路径必定通过时效/几何/预算门。真正剩余阻塞应分别报告为clock-domain覆盖、完整source/horizon支持、姿态UNKNOWN、Max配置、独立组及研究质量，不能继续归并成“缺GNSS”。

## 8. 自审及静止证据范围

自审已覆盖：原/继承spec时钟条款；所有已定位的deadline生产与消费类别；同域bracket数学；未来H_D不可由past slab或sim timeout推导；wall/sim及suspend/restart；同模型/同阈值公平性；新版本与旧守卫/原件隔离；实际与CPU证据分级。输入SHA与检查范围写同名JSON，hash仅标本次读取版本，不表示活动R3实现被验收。

没有调用外部授时、网络、模型、renderer、physics、decoder，没有执行原件验证器或修改任何实现。结论是设计建议，尚未实施、校准或达标。
