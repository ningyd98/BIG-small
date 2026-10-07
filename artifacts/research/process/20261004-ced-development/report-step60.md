# 第60步：完整标记时域采集、严格读出与来源链路软件

## 完整实际采集与唯一严格读出

root唯一完整采集session88431退出0，wall 674.844278秒，GNU峰值RSS440252 KiB；没有重试、watchdog或模型/provider请求。4807次回调及分配全部保存，范围0–4806，4806物理步进、9个教师动作，最终SimulationS为20.02500016020091。原件4829文件、534140506字节，其中帧压缩载荷417481375字节。缺帧、额外帧、失败分配、发布错误与采样间隔违规均0；206冻结输入未变。

严格reader唯一session1633退出0，wall 684.092848秒，GNU峰值RSS301588 KiB。4807个新raw逐帧验真并各解码一次，OBSERVED4807、coverage1.0；最大保存/相邻OBS间隔0.004166666700001542 SimulationS，小于既定0.005界。原4618个OBSERVED全部保留，189个UNKNOWN全部恢复，没有新的UNKNOWN。原201稀疏子组是本次4807中的子集，不能另加分母。9822受保护输入在读出前后保持。

四份完整记录流physical4807、actuator4806、commands743、scorer4807，各自所有保存字段逐行相等，唯一排除字段episode_id。旧full未保存全部qpos，因此不能声称全部内部物理状态或独立反事实重放相等。采集时写出的NOT_RUN及第59步RUNNING均保留为当时快照，当前以reader终态与严格报告为准。

## Astra元数据补验及最终独审

原独审脚本直接哈希header三个字段，遗漏冻结dataclass的dictionary默认字段，4807行全部被误报；原报告、失败清单和首行诊断保留。按[Astra round62计划](astra-rounds/round62-marker-review-digest/plan.md)，仅执行一次标准库binding元数据补验，从冻结AST默认与header动态构造规范值；同一遍读新derived身份/登记字段并核对9853287字节及SHA，4807行的status、observation_id、checksum、registration_hash四项均匹配，findings0。37个受保护metadata/source/archive前后未变；decoder/raw/旧derived/project import/test/runtime/model/network/Git均0。其他已过检查明确引用旧证据，未重复。

[最终独审](astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/round62/final-review.md)及[局部步骤报告](astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/round62/step-report.md)保留完整失败→计划→补验时间顺序。最高仅本次开发采集保存全帧时域的可观测性通过，全部非晋升限制保持。原失败报告的FAIL_OR_UNAVAILABLE不回写为PASS。

## OC2第一项软件交付及独审

原Task1缺接口RED40失败按计划保留；首次GREEN38通过/2失败与Ruff/格式/mypy原始失败亦保留。按Astra round61限定修改五个新文件：精确分支拒绝测试保留健康真实worker/lease对照，仅新增真实origin None守卫，其余静态修正不改变行为。最终唯一40项GREEN全部通过（60.04秒），Ruff、格式及mypy均退出0，89项非白名单受保护输入未变。15个临时SQLite数据库中15job/15lease/15attempt；CPU已有真实SQLite/lease/私有登记与借用handle，实际dispatch/capture/physics/model/network/decoder均0。capture实现仍为Task2待实现stub，不能借它的异常证明来源授权。

独审唯一CPU API探针21场景通过（12.896514秒），两份临时DB/job/lease/attempt与2个source allocation（1成功、1失败）保留；作者40与独审21不相加。独立零副作用default CLI及只读闭包225来源/904导入边通过，但原CLI stdout和部分独审原输出字节未保存，只能引用工具观察，缺少的SHA不补造。

独审AST比较器误删原已有origin赋值并改写return，产生false；审查员先写corrected及provisional报告，root随后暂停验收。这些材料保留，不能追溯称已获Astra批准。按[Astra round63计划](astra-rounds/round63-oc2-review-ast/plan.md)仅做一次严格静态补验：原origin赋值和return不变，只去除精确新增None守卫后比对全app AST，核对import且无需规范化，完整残余AST精确相等；原160输入前后保持。[新的最终独审](astra-repair-execution/OC2/independent-review-task1/round63/final-review.md)最高PASS_SCOPED_SOFTWARE_OC2_TASK1，实际来源、capture实现及Task2/3仍未由此验收。

## 后续及研究边界

root接受两个限定终审后另登记[来源窗口授权](astra-repair-execution/OC2/gate-B-root-acceptance.json)：marker实际采集与reader均已退出，冻结原件保留，允许按原OC2 Astra计划进入Task2/3软件实施及worker小型分支。真实prefix-1仍需全部软件/静态/冻结及独审门通过，再由root一次执行；当前实际OC2=0，不借源窗口授权声称source-positive。teacher/backend/OC1修改不在该授权范围，恢复teacher工作仍等待其保护输入窗口。

当前仅保存帧全时域开发可观测性PASS_THIS_FULL_HORIZON；sampling PASS_RECORDED_SIMULATIONS及raw VERIFIED_FULL_RAW_AND_RECORDED_TRACE不等于连续运动证书。continuous_visibility=NOT_ESTABLISHED、continuous_motion=NOT_CERTIFIED、stability=UNKNOWN、future_stability=UNAVAILABLE、source_authenticity=UNKNOWN；native NOT_PROMOTED，几何/角速度界null、支持校准组0、独立校准组false，UTC/SI精度尚未证明，formal_accepted=false。九独立组、三消费者闭合、G1及INITIAL/METHOD/FINAL继续未验收；T12/18、T13并行，边缘模型后置，硬件NOT_STARTED、S3/S4 LOCKED。恢复wall-Rcap仍计划阶段，实际0002未执行；Max当前检查范围无enabled兼容profile，历史35次调用保留，不推断用户其他环境无key。

Git本地仍be1c10cd596926d0184d7c13268ae3c3e22109d0；原383文件/20112981字节具体公开载荷等待批准。自动审批两次拒绝，push执行0；远端最后核验24ddf13193a1547edeab39165846ff716a0b5f3d。本轮新报告/源码尚未commit/push，未改变待批commit。raw/运行DB仍本地，清单与派生报告不作完整远端复现包。

原始终态及严格证据：[采集进程](astra-repair-execution/R01/marker-v4-full/actual/execution.json)、[完整采集分母](astra-repair-execution/R01/marker-v4-full/actual/root-terminal-summary.json)、[reader进程](astra-repair-execution/R01/marker-v4-full/actual/reader-execution.json)、[严格读出](astra-repair-execution/R01/marker-v4-full/offline/offline-verification.json)、[OC2软件局部报告](astra-repair-execution/OC2/implementation/round61/report.md)。
