# R07 固定机会与200实际故障生产路径审计

2026-10-05。结论：现有独立汇编/验证器和实际 T5 教师可复用，**池驱动的 R07 真实生产入口尚未实现**。下一项是新增单组有界 collector，先完成锁定新组 recovery-0001 的一次实际注入、九动作、原始步进控制和独立评价；不等待在线 T13、UTC、Max 或边缘模型。当前 R07 正式物理证明为0/200；历史1开发组不得移入正式池。

本轮只写本目录 report.md/json；未改 core/tests/rootdocs/Git，未运行 renderer、physics、provider、decoder、network 或测试批次。按 executing-plans、systematic-debugging 的源头追踪与 verification-before-completion 核对实际入口/原件边界。精确文件 SHA、命令、观测结果和后续参数见 report.json 的 pins/commands。

## 原方案、配额与域边界

原20261004规格§5要求固定机会及200真实故障可恢复性证明，普通无故障成功不算证明；§8行119–123保留池隔离、扰动层、固定顶视320×240、独立物理门槛及Rcap60秒。原20261003规格§5.2规定三任务×四网络层及速度0/20/40mm/s、深度噪声0/2/5mm、无效0/10/30%、遮挡0/20/40%，未规定恢复池的多故障类型或各类型配额。当前 recovery_faults.yaml 是明确登记的 TARGET_MOTION200，速度.02m/s、持续1s，按 canonical ordinal 正负Y交替，所以100正向/100反向。不能把 backend 枚举里的 slip/estop/mass/friction 当成已经预注册的配额。

eligibility只检查目标及目的区包围盒位于固定workspace和xy半径，不等同IK可行或可恢复。最多5次是有界上限，不能隐式重试、改几何或删除失败。达到不足200仍INCOMPLETE，不能改成160或仅成功集合。

首次审计曾由R1尺寸推断R7也须640，这个推断已撤回：正式原规格raw320×240与ced_roles.cloud.image_size320×240的传输界应分别绑定；R1实际640×480是已排除开发诊断域。保持同顶视camera/controller不要求把R7原合同改为640，也不允许降采样旧原件充新组。vision.messages已有双PNG同尺度NEAREST传输转换和回到原米制深度像素中心的映射；原RGBDObservation的depth/calibration身份不因此改变。这是云transport路径，不是新raw采集。离线T5本身0云调用，不需要此转换。R1noise0与R4native默认noise.001也不冒称同域；新R7使用锁定SceneSpec、明确SimulatorConfig、原320capture和注册扰动日程。Qwen3.8-Max、OpenCV及现控制器边界不变，边缘后置。

## 真实入口与缺件

| 入口 | 已实现 | 不能替代的部分 |
|---|---|---|
| protocol_evidence.prepare/verify | 原件归档、标签/注入/动作/控制/全步安全重算，2400/200和3260完整拓扑，离线角色限制 | 不运行仿真，不生成缺失成功 |
| write_recovery_source | 被动转换detached完整观察、actual ActionResult和实际command_seq | 不采集、不注入、不步进；命令不能省前缀或重编号 |
| datasets/rgbd/generator.py | 有界感知场景采样、真实捕获、失败journal | 不执行T5/恢复故障，不输出R07命令/控制轨迹 |
| generate_rgbd_trajectories.py | 真实T5 NORMAL/NO_CONTACT及独立评分、旧20/42批完整保留 | 自己的smoke场景，不读R07锁定池，不注入故障；输出PhysicalSample不是完整raw控制证明 |
| collect_raw_development.py | 固定旧开发组真实TARGET_MOTION后T5完整5368状态/5367控制/9动作 | 固定seed/路径、无任意assignment/attempt入口；不能重跑或复制充正式组 |

当前teacher.physical_observer覆盖entry及每个原物理步；action_observer传actualresult、start/end、1-based半开command range；backend actuator hook是next-completed-stepID加PRE-step时刻，保留q/bias/targets/gains/ranges/ctrl/finger。沿这些现接口接现teacher，不能嵌套第二physics observer或新增执行器。故障的真实机制是水平外力和速度反馈，实际STARTED/FINISHED及原始位移证明存在，不写目标位姿。正式collector必须使用direction_y；旧脚本写direction只因为第一组默认+1而碰巧正确，直接循环会让负向配方错用默认正向。

历史T5修复20分配19成功和负控失败、新42分配40成功/负控失败/安全失败均不算R07新故障组；独立抬升50mm、保持.5s、释放后完整物体稳定1s和安全门不变。历史验收是其来源版本事实，不能自动升级成当前source通过。

完整机会仍缺实际collector：固定候选MOVE_TCP target=[assignedx,y,.16]、radius.02、timeout8s；真实RGB-D/实例映射/校准/三个pass statehash与reset-terminalcontext，actualresult/dispatch/control和全33碰撞范围必须同源。原始与扰动后观测均须保存，注册扰动及提交时刻不能在看比较方法结果后补定。现prepare只归档已知context文件，现teacher adapter也是教师专用；必须补实际candidate绑定及双原件/日程归档接线，不能只扩summary布尔字段。

## 当前池和历史隔离

旧pilot-v2/pools为3140，缺selection120，不能作v2COMPLETE。t8b-module/fix-round-1-dry-selection/pools及dry-selection/dry-foundation三份同SHA `e86ac4858fffb0040301c38a0481da7261bece6070e3531cfe9fc2e863c10618`，完整3260但只是同一批assignment副本，均无_evidence原件来源，不是INITIAL或实际新组。定向CPU检查其全部池与注册101排除、旧pilot-v2foundation120交集均0；这只证明这两个输入边界，不能宣称完整训练/标定/选择/开发历史已排除。

R07/pools.json目前不存在。应先锁定其完整v2拓扑、全部实际使用组及component关系、candidate/observation/fault日程和eligibility/attempt规则。拟定新seed2026100507仅是后续参数建议，本轮未生成/选择/写池，旧分配池完整保留。R1的4807帧、9动作和其来源component均不能充independent/fault组。

## 下一 owned 实现与唯一首批

建议新增 `research/protocol_generation.py`、薄 `scripts/generate_rgbd_protocol_evidence.py`、CPU源合同 `tests/test_protocol_generation_sources.py`。当前未提出任何立即核心验证器修复：本轮没有合格新的actual-source false-PROVEN CPU反例，不能把维度误判或缺CLI包装成已证实core bug。新入口测试先覆盖旧组/无故障/错direction/失败原动作/截断/命令前缀/重入、预算和全部分配原件保留，再最小接现teacher及observer。

首批只分配锁定recovery-0001，attempt1，renderer在途1、云请求0、隐式重试0。独占fresh session，apply_scene只在reset；从reset0保留每步，120settle；注入.02m/s、1s、direction_y+1，真实FINISHED后启动NORMAL教师settle_steps0。等待上限ceil(1/dt)+1=241步，dt=.0041666667；老师entry重复只能去除完全相同快照。九动作原超时及dwell不变，faultstart+60s为总物理恢复期限，不能只凭teacherstart后的60s换G4口径。全迹和原始command_seq1..last、PRE-stepactuator保持，失败中断也先保全alloc/partial原件，适用独立评分后再汇编。

唯一建议首批命令如下，**CLI与锁定池均待实现，现阶段不得运行**：

```bash
MUJOCO_GL=egl PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/generate_rgbd_protocol_evidence.py --pools artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/pools.json --recipe configs/research/recovery_faults.yaml --kind recovery --assignment recovery-0001 --attempt 1 --output artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/raw/recovery-0001/attempt-1 --execute-once
```

首组失败/排除/未完成就保留并结束此batch，不调target/direction/seed、不隐式再挑另一组。首组原件及source-pin独审后，再按预注册有界库存串行走0002..0200；其他机会collector软件可独立继续。本轮只完成审计，不把尚未实现命令描述成可执行现货。

## 参数、成本与验证

拟定首批wall上限1800秒、保留字节2GiB、磁盘free reserve10GiB；这些是待实现及冻结的操作预算，不是已测吞吐，也不改变研究门槛。实际R1完整批summary为915.7645秒/4807captures、文件4829/519,937,924字节，只作完整采集成本参照；R07T5通常仅10boundary captures，不能用R1除帧后的单价或旧失败均值承诺200批次时间。历史fault原始6文件23,917,325字节同样仅容量参考。首个新完整source实测wall/peakRSS/raw+汇编copy空间后再给200库存与最大5attempt1000记录上界；1000只是记账天花板，不授权重试。

新鲜只读CPU核对：两个poolmanifest数量和有限交集、实际bootstrap尺寸、R1文件stat/summary、旧开发fault0至1.000000008s及commandseq1..831端点，七个named源AST parse退出0。以前fix-round2的52test日志是历史证据，本轮没有重复该batch或任何full suite；raw证明也未重复完整审计。四个此前owned源码SHA均与fix-round2一致。report.json列精确输入pins、每种命令结果及NOT_EXECUTED实际命令；报告落盘后再校验JSON结构、pins和目录只含两份新report。
