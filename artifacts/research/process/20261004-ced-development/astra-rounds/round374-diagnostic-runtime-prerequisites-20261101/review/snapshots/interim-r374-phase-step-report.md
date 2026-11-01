# R374 诊断运行前置与编排恢复（验证进行中）

本轮承接用户“重跑全流程，继续总结问题”。实际 gpt-6-astra 的[计划](plan.md)、[组05余额解释](scope-clarification.md)和[执行前顺序解释](scope-order-clarification.md)共同限定本轮工作。产品、测试断言、冻结登记和历史原件不在修复范围；本轮调整的是新诊断的环境、输出位置、停止/续跑与覆盖记账。

## 原始问题与证据

R373普通组01–04分别到900秒上限，当前节点依次为phase12运行真实性、operational_windows五秒边界、dashboard websocket和level0能力路由。它们共同表现为未完成，但不能据此认定同一根因。组04另有9个writer-binding失败，退出观测器的finally读取缺失的BIGSMALL_R223_RESOURCE_ROOT，可能掩盖更早异常；源码还要求BIGSMALL_R223_CASE_ROOT。

原父进程仍位于旧执行环境，而新工具已使用full-access。仅凭等待状态不能认定沙箱是全部根因。level0用例自身也设有独立artifact目录，不能把其超时直接归因于扫描全仓库。旧运行已在R373保留stdout/stderr、事件、调用参数、源检查及真实的超时结果。

## 实施与已验证结果

1. 按实际PID、启动时刻、命令行和所属进程组核对后冻结旧R373父进程，停止当时运行的组05子进程，再终止父进程并由原session回收。原组05保留156通过、40失败及1个setup-only节点；没有向旧目录补造result.json。见[停止回执](process/interruption-receipt.json)。
2. 新R374 runner为每个阶段建立独立R223资源/案例目录，以及model-control、simulation-runtime和dashboard输出路径；这些环境变量在导入前设置。closure继续使用原R235前置插件、相同legacy golden与兼容命令标签，真实运行身份由本轮目录和invocation记录区分。
3. 唯一强制新进程诊断重跑原level0节点，pytest通过，外层2.501秒。它证明单例在新隔离环境可完成；旧沙箱影响与测试顺序影响仍未分离。条件性的最小框架探针未触发，可选顺序前缀探针未运行。
4. 九个T3节点保持原600/3600秒诊断上限并优先串行运行。memory完整UTC已于2026-11-01T04:19:35Z完成：1通过、0失败/错误/跳过，pytest2355.490秒，外层2356.436秒；三个场景原始case、资源侧车和JUnit齐全，2647项资源均观测到清理完成，清理错误为空，源前后无漂移。详见[限定结果](reporting/utc-memory-result.json)。SQLite于2026-11-01T04:58:50Z也完成1通过，pytest2353.836秒、外层2354.930秒；三个场景、2639项资源清理完成，错误为空、源无漂移，见[SQLite限定结果](reporting/utc-sqlite-result.json)。T3九项最终为4通过、5失败、0超时；全部正常退出回收，前置通过、源无漂移，见[T3结果](reporting/t3-results.json)。R223补齐资源目录后的唯一限定复验9项全部通过，pytest44.032秒、外层45.009秒；原9项失败仍保留。
5. 原从未启动节点的续跑候选已冻结。组01–04各至多300秒新增尾部额度；组05从原900秒保守扣除31秒，余额869秒；组06、closure、MuJoCo和浏览器沿用原额度。API模块至多60秒，其余普通模块至多300秒，并受各组余额、16秒清理预留及原八小时总墙钟约束。
6. Astra允许在尚未消费续跑额度时，仅将组01/02各自原超时模块的其余候选稳定置后。新[continuation-v2清单](continuation-v2/planned-stages.json)与旧版具有相同完整子项对象、节点多重集合和预算，脚本逐字节相同；其他顺序保持。旧等待器经身份复核、SIGSTOP再次确认仍未执行，再单PID终止和原session回收；正在运行的T3没有收到信号。见[置换验证](continuation-v2/freeze-validation.json)、[替换回执](continuation-v2/waiter-replacement-receipt.json)与[新等待器记录](continuation-v2/launch-receipt.json)。

## 本轮新增 T3 失败（独立阶段继续）

两个启动节点均已通过（memory外层242.040秒、SQLite245.041秒），但三个终态故障用例均失败。commit_close在`fault["fired"] is True`处失败；只读数据库记录任务为INTERRUPTED、operational_epoch_ended，具体原因只剩original worker poll ended，确认行0。故障钩子未到达，早期具体异常尚未从现存证据恢复，不能将此直接判为发布确认漏洞。见[只读审计](reporting/terminal-commit-close-readonly-audit.json)。

confirm_timeout和prior_bound已经产生accepted=false的拒绝记录，分别是broker请求超时和跨原租约边界；随后公共读取在ExperimentManifest校验处失败，缺6个必填字段。继承的测试工厂创建任务时没有完整manifest，数据库实际为{}，公共service严格校验它。拒绝记录证明本次观察到的否决行为，但完整公共读取断言尚未完成，这两个用例仍记失败。见[确认超时审计](reporting/terminal-confirm-timeout-readonly-audit.json)与[期限边界审计](reporting/terminal-prior-bound-readonly-audit.json)。memory与SQLite正常发布对照也同样在空manifest的公共读取校验处失败；两者SQL均为SUCCEEDED，各有1条CONFIRMED及结果文件，因此有写入证据但不能宣称完整公共读取通过。其余流程继续，本轮不顺手修复。

## 尚待终态及验收边界

T3与R223复验已结束，普通六组续跑也已完成预算记账；closure、MuJoCo和浏览器仍在继续，随后生成最终逐节点统计。实时统计见[覆盖清单](reporting/coverage-manifest-live.json)；4732个唯一Python节点为分母，前端及浏览器另列。历史失败/超时与新环境诊断通过分开保留，未启动节点不计通过。R371相关5项短回归已全部取得本轮新通过记录，见[短回归核对](reporting/utc-short-regression-live.json)。

两个后端完整UTC通过都是CPU软件诊断结果。该用例在每个新场景启动前安装UTC偏移，并包含晚返回期限场景；不等于同一真实运行任务中的系统时钟跳变证明。两后端外层合计4711.366秒，已超过原双backend合计600秒验收额度，本轮放宽后的诊断结果不能代替原验收。当前源清单还包括既有未提交local_temporal性能候选，不能把结果归给干净的UTC修复提交或宣称候选有受控性能提升。

44个标记相关失败（关联36、范围集成8）已只读定位到10月5日冻结源码哈希与10月17日现行源码之间的版本不一致；旧登记未改写。资产注册表另有1项场景SHA不匹配，见[资产只读审计](reporting/asset-manifest-readonly-audit.json)，它与标记源码登记是两个独立绑定问题。R223在缺失finally环境下的原9个失败与本轮补齐环境后的9项通过分别保留。

工作台模块6通过/1失败，首事件run_state预期却读到job_created。新诊断runner的模块级SIMULATION_RUNTIME_DB覆盖各测试自己的artifact目录，已由实际Astra制定[R375计划](../round375-diagnostic-database-scope-20261101/plan.md)。新adapter与90秒外层监督器已复核READY，只能在当前整个continuation终态后同序运行原7节点一次、子进程最多60秒；目前未执行。其余新失败只汇总，相关修复须另经Astra计划。

真实模型、硬件、独立校准、INITIAL/METHOD/FINAL与正式研究验收均不能由本轮软件诊断替代。完整raw、运行数据库及资源侧车继续本地保存，选定的小证据与清单不代表完整远端复现包。
