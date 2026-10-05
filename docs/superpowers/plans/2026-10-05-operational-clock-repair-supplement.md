# Astra 计时依赖审计的执行补充

本补充由root依据用户指定Astra的 [只读审计](../../../artifacts/research/process/20261004-ced-development/astra-repair-planning/clock-dependency-review.md) 落为后续执行顺序。审计是设计证据，本路径尚未实现或验收。原 [10任务、48检查项修复计划](2026-10-05-astra-repair-plan.md) 保持原件；下列四项是新的计时路径任务分解，不把其数量与原执行检查项直接相加。原18主任务、主线T12/18、T13并行和边缘型号后置均不改。

**修订工程依赖：** 单机仿真实证可走原严格UTC路径，或者经过完整独立验收的新 `simulation.operational-time.v1` 路径。外部校准UTC不再作为所有离线/单机仿真实证的唯一前置。旧UTC工厂、RawV3原件/判定和守卫保持；新scope不能给旧UTC字段填0、将UNKNOWN改为VALID、回填旧帧或伪造九个独立组。

## 必须先冻结的合同

- D是冻结平台的真实操作计数域；S是同backend/episode的仿真时间/physics step。请求端到端、TTL、PCSC周期、任务/恢复wall预算使用D；0.005秒采样gap、物理抬升/保持/放置稳定使用S。记录实际 `(D_BEGIN,D_END,S_BEGIN,S_END,kind,step,owner)`，不得把S秒当D秒。
- 真实事件与当前检查点的同域括号分别为 `[c−,c+]`、`[n−,n+]`；在原始因果关系成立后，年龄上界为 `(n+−c−)/10^9`。未知来源、跨域、倒退、未来/逆序先拒绝，不用midpoint或clamp隐藏。普通/condition五秒、接收5000ms和未来1000ms规则不放宽。
- 原任务起点括号 `[b−,b+]` 和固定预算T产生保守截止 `b−+T×10^9`。deadline等值拒绝；重观测、晚回复、新event、重启或重试不刷新截止。真正事务及dispatch前重新读当前D。所有rounding向拒绝方向。
- 实际startup authority绑定计数API/实现、boot/epoch、app、worker、capture和原lease/fencing；caller字符串、PID、readonly/hash或resolution不是授权或SI精度。时钟选择须有实际平台语义证据，完整wall预算必须含suspend；缺此支持不验收。
- 单机操作计数域不保证SI/UTC精度、跨机时间或真实机器人安全。真实非空外部UTC期限、第三方lease/证书/JWT及远端图像仍走原严格路由；没有域间桥接证据则不支持新域。
- 历史年龄和当前比较不能生成未来执行界。sim timeout不得充当完整未来 `H_D`；经验平均/割线不得充当运动上界。几何/完整动作source和至少九个独立支持组、coverage .9、10mm及全部统计门保持。强制完整future窗口而缺对应支持时，新域也必须UNKNOWN。

## 四项有序任务

- [ ] **OC1：新域类型、reader与边界数学。** 新增独立的operational-domain/bracket/deadline类型及最小reader，不复用datetime冒充UTC。来源仅由实际startup工厂签发；记录时间实现与suspend/重启scope。先取得真实接口的CPU RED→GREEN：5秒/5秒+1ns、deadline等值、缺pair、foreign domain/copied handle/boot漂移、合法重叠、UTC跳变仅诊断、未来/乱序及原deadline不刷新。此步仅SOFTWARE，不给应用native源授权。
- [ ] **OC2：单应用真实来源正分支。** 复用独审通过的R03 single-recorder/live-handle/原RESET tee最终版本，先持久化预注册source/recipe/group库存，再登记真实事件。一次新scope实际预注册→RESET→120SETTLE→真正capture→当前D；保存原始括号、同S状态、cached acquisition身份、全分母/失败/source pins。原R03 A/B prefix仍按原合同另记；新D路径不等待校准UTC。首次真实来源不是九组、消费者、G1或正式验收。
- [ ] **OC3：全部窗口闭包与完整动作source。** 统一相机/marker/condition、三native入口、planner与supervision本地签发/返回、任务/grounding/binding/ACK/start/effect、PCSC/请求等待、budget、repository事务、SQLite lease/heartbeat和publication。旧域/外部UTC输入保留严格语义；并行worker不能混域授权。先单schema端到端CPU正负链，再限定actual闭环和真实restart/suspend证据。完整S/D horizon及geometry/motion支持仍须按R4/R5独立重建，未知保持UNKNOWN；不能只改一处now就登记完成。
- [ ] **OC4：共同研究协议和成本。** 共同主方法/B0—B5冻结同一域、映射和秒刻度，实测请求/等待/render/动作完整wall成本及fault-start Rcap守卫，不调时速或遗漏休眠。重新依合格B0计算Tcap，声明单机仿真operational秒范围；R6真实Max与R7固定机会/200教师独立推进。合格B0→INITIAL→METHOD→功效120→FINAL→正式统计/复现的原顺序不变，旧FINAL拒绝不能仅删guard。

OC3的必要改动闭包以Astra审计§7中的实际文件定位为准：`vision`的action/execution/supervision/worker/owner/marker、`edge/evidence`的models/validator/conditions、event-autonomy的bootstrap/supervision/owner/verification、recovery router、simulation worker/repository、research clock/native calibration等。先审查已存在合同和真实消费者，精确修改受影响路径；不重造控制器、执行器或全仓重复测试。

## 与当前执行的衔接

R01完整V3原件已通过，但189姿态UNKNOWN仍在；新75mm标记仅固定201帧诊断，不能作为0.005秒连续证明。R02/R03只提供条件历史UTCslab，B后now保持UNAVAILABLE。R07首组原件独立复算通过，1/200；其模拟Rcap与wall计时缺口要单独补修，不能用源代码freeze代替实际wall测量。Max当前可启动配置缺件继续独立报告，历史35次调用不冒充新角色probe。

实施每项按原约定保存限定报告、原始失败/分母、实际调用及输入/输出SHA，独审静止版本后root汇总阶段总结并显式路径提交推送。CPU、真实来源、实际消费者和研究门分别记账；新域完成前不登记R4/R5、UTC、G1或整项目DONE。首次actual与renderer/GPU队列仍串行，真实硬件NOT_STARTED、S3/S4 LOCKED。
