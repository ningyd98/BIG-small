# 第56步：Astra计时修订与两项真实修复先导

**本步取得了标记修复的直接实测证据、真实RESET前缀和首组故障教师原件。** 全研发仍在进行，不将软件PASS、稀疏201帧或1/200来源升级为正式研究完成。原18主任务不重编号，主线T12/18、T13并行，边缘型号后置。

## Astra计划与补充依赖

[用户指定Astra的原修复计划](../../../../docs/superpowers/plans/2026-10-05-astra-repair-plan.md)共10任务、48执行检查项，原字节不改；第54步已交付。新的[Astra计时审计](astra-repair-planning/clock-dependency-review.md)复读原研究合同，未发现外部校准UTC必须作为全部单机仿真实证的唯一前置。root按审计落为[四项计时执行补充](../../../../docs/superpowers/plans/2026-10-05-operational-clock-repair-supplement.md)：新域reader数学→真实startup/RESET/capture来源→全部窗口/消费者与双域动作支持→共同研究协议。新增四项是另一层任务分解，不简单相加为52个原执行检查项。

新版本simulation.operational-time.v1仅为计划。普通/condition五秒、5000ms接收年龄和1000ms未来规则、0.005模拟gap、10mm、coverage .9、全部预算/统计门均不放宽；旧UTC路径保持原语义及UNKNOWN。未来完整耗时界不能由历史A/B或sim timeout推出，suspend/restart及所有消费者/lease必须覆盖。审计0代码执行/0actual，不能作为新域已验收。

## 新标记受控试验

范围缺陷R01-V4-RANGE-01经独审关闭后，root仅执行新fix-round-1/pilot-protocol/attempt-1一次，退出0。120settle、9动作、2dwell、4806物理步、743控制及4807回调完整；201固定选中帧全部保存，失败0。采集内部wall49.518431729秒，GNU整个进程wall50.02秒、peakRSS379996KiB。

唯一离线严格解码201次，**201 OBSERVED / 0 UNKNOWN / 0异常**。固定旧201中的189 UNKNOWN全部在新试验对应时刻转为OBSERVED，12健康对照保持。新最短marker边27.0—30.016662像素、median28；ID7/75mm/局部X160mm为冻结的联合变更，未分别证明尺寸与偏移的单独贡献。

原严格detector未改，真值只参与离线来源/物理复核，不进入检测。新旧4807物理状态、4806执行器状态、743命令及4807scorer记录，仅去除episode_id后逐字段完全相同；该比较限已记录字段，旧full qpos缺失仍不补造。223新raw/54415036字节及266输入before/after不变。相机调用摘要213，实际render总数没有测量，保持null。

reader GNU wall41.75秒、peakRSS2389828KiB；17项有界CPU与窄静态通过，独审仅软件与已有readout、不重播201解码。**稀疏最大gap2.1166666836秒大于0.005，连续姿态、native、未来稳定性和独立校准组不成立。** 下一次支持单独冻结的full-horizon v4，不直接将本次升为连续证明。见[标记离线报告](astra-repair-execution/R01/marker-v4-preparation/fix-round-1/offline/report.md)、[限定独审](astra-repair-execution/R01/marker-v4-preparation/fix-round-1/offline/independent-review.md)及全部201行输出。

## R03实际RESET来源，时钟保留失败

31owned与16窄回归、定向static独审通过后，root唯一启动prefix-1，退出0。真实SQLite job/lease/attempt进入原worker早期source-only分支，RESET和120SETTLE、2缓存帧、488clock pair及486operation事件保留；explicit acquisition/planner/model/action request均0。公共原件reader独立返回VERIFIED / prefix_complete=true，56非runtime-DB文件/7989524字节不变。

实际A发送1请求并收到1包；包缺冻结draft08必需NONC，在字段检查阶段拒绝、尚未进行签名验证。B如实SKIPPED_A_UNAVAILABLE，无重试。收到的远端身份未认证，不能断言全部服务不可达或公钥错误；严格守卫保持。历史interval为空，width/TTL比较null、issuer UNVERIFIED、current/nativeUTC和consumer feasibility UNAVAILABLE。GNU wall2.47秒、RSS221932KiB。见[实际诊断报告](astra-repair-execution/R03/actual-prefix/report.md)及[软件独审](astra-repair-execution/R03/implementation/independent-review.md)；完整prefix不是adopted RawV3、任务执行或九组校准。

## R07首组实际来源与最小迁移

root执行唯一recovery-0001/attempt1，退出0。真实TARGET_MOTION20mm/s/1秒/+Y，测得位移19.102003mm；原九动作教师完成，7047物理步/7048原始状态/7047执行器记录全部保留。严格原件复算全proof与原result相同：SUCCESS/SCOPED_NO_VIOLATION、抬升91.853706mm、保持0.629167/放置稳定2.150000模拟秒。

fault→终态28.862500231模拟秒，GNU整个进程wall17.45秒/RSS410528KiB是首组真实fault→终态wall的保守上界。实际原始17文件/101586767字节（含result）；48限定输入before/after不变。**1/200已执行，199未执行、机会collector未实现、G4未验收。** 见[首组实际及独立复算报告](astra-repair-execution/R07/actual-first-attempt/report.md)。

末尾检查重复加recovery_start由严格原件和真实guard AST边界反例确认；最小删除该项，首组前后均低于60、不重标原PROVEN。新successor显式继承66570…原协议全部3260rows/6payload/seed，共享原allocations namespace，首次attempt仍消费且canonical计数1/199/200；旧包正确拒绝source漂移。17项定向CPU及窄static、[successor独审](astra-repair-execution/R07/producer/duration-fix/successor/independent-review.md)通过，未执行0002。

当前逐步故障门仍是sim60、外wall1800；后199正式wall-Rcap守卫尚未实现。下个独立切片须在实际fault起点登记wall原件并于step/effect/terminal保守检查，不能以冻结或模拟秒冒充wall保证。successor软件验收不关闭此缺口。

## 当前修复队列

| 原任务 | 已取得证据 | 下一缺口 |
| --- | --- | --- |
| R1 | 完整V3采集/离线原件验收；新v4稀疏201全可识别 | 单独冻结的v4全程采样/连续门 |
| R2 | pinned Go/Python causal slab和pin补修软件PASS | 真实兼容响应与相应scope精度，不替代在线now |
| R3 | 软件独审、真实RESET/120前缀 | 严格UTC本次不可用；OC1—OC3新路径另验 |
| R4 | 旧合同保持 | 真实有限source正分支、至少9独立支持组 |
| R5 | 软件消费者已有，native不准入 | 同一新来源/全部窗口/完整horizon接3入口及G1 |
| R6 | 历史35calls不变、当前预检已有 | 当前可启动Max角色配置及4真实probe |
| R7 | 3260原池、首组原件、共享ledger successor已审 | wall-Rcap原件/守卫、余199、固定机会collector |
| R8 | 旧负结果保留 | 资格满足后的四周期B0、新120、INITIAL |
| R9 | 已有局部软件不重写 | 实际风险/恢复闭环及METHOD |
| R10 | 原FINAL拒绝与统计软件保留 | METHOD后另120功效、FINAL、正式/复现 |

## 报告与Git

本步更新六份当前文档并追加阶段总结，保留第54—55步历史快照。限定交付选择静止已审R03源/CLI/tests/配置、worker3hunks、完整非DB prefix原件；R07已审生产器/新旧协议和必要metadata/source档案/失败/独审；v4资产/原新软件/selection/source/freeze与派生报告、Astra补充及本步文档。新增UTC路径仅计划，未改现有consumer。

完整旧V3约519.9MB、新v4约54.4MB和R07约101.6MB批量raw仍本地；所选清单/派生输出不是完整远端raw复现包。DB/secret/模型权重/SDK/活动代码不暂存。root按每个显式路径SHA、staged blob与差异核对后提交推送，远端终态另写git-delivery-step56.json。边缘型号后置，真实硬件NOT_STARTED/S3/S4 LOCKED，formal_accepted=false。
