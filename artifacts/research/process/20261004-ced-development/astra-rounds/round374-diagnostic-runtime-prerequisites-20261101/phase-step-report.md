# R374 诊断运行前置与编排恢复（诊断已结束）

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

## T3 失败分类

两个启动节点均已通过（memory外层242.040秒、SQLite245.041秒），但三个终态故障用例均失败。commit_close在`fault["fired"] is True`处失败；只读数据库记录任务为INTERRUPTED、operational_epoch_ended，具体原因只剩original worker poll ended，确认行0。故障钩子未到达，早期具体异常尚未从现存证据恢复，不能将此直接判为发布确认漏洞。见[只读审计](reporting/terminal-commit-close-readonly-audit.json)。

confirm_timeout和prior_bound已经产生accepted=false的拒绝记录，分别是broker请求超时和跨原租约边界；随后公共读取在ExperimentManifest校验处失败，缺6个必填字段。继承的测试工厂创建任务时没有完整manifest，数据库实际为{}，公共service严格校验它。拒绝记录证明本次观察到的否决行为，但完整公共读取断言尚未完成，这两个用例仍记失败。见[确认超时审计](reporting/terminal-confirm-timeout-readonly-audit.json)与[期限边界审计](reporting/terminal-prior-bound-readonly-audit.json)。memory与SQLite正常发布对照也同样在空manifest的公共读取校验处失败；两者SQL均为SUCCEEDED，各有1条CONFIRMED及结果文件，因此有写入证据但不能宣称完整公共读取通过。其余独立流程已按原计划完成有界诊断，本轮未修复这些问题。

## 最终覆盖及验收边界

continuation-v2于2026-11-01T07:05:18Z完成235个唯一子项记账：91启动、144NOT_RUN_BUDGET；91份清理回执均无残留，原父进程已退出。closure01/02各1个未完成、27个未启动；closure03为26通过、1未完成、2未启动，三个阶段均约884秒到限。MuJoCo关键组24通过（pytest1.875秒）。默认浏览器21通过、18未通过、1跳过，研究页面3通过；[浏览器账本](reporting/browser-results.json)与[草稿合同审计](reporting/browser-draft-contract-readonly-audit.json)分列软件fixture及真实研究边界。

随后R375唯一同序7节点对照通过：仅移除模块级SIMULATION_RUNTIME_DB并迁移新输出，内层验收true，外层19.925秒且无超时/错误/残留，6个生成DB均位于per-test目录；原6通过/1失败保持。见[R375报告](../round375-diagnostic-database-scope-20261101/phase-step-report.md)。

最终4732唯一节点为1845通过、54失败、17未完成、2743阶段停止前未轮到、71未运行、2被选择条件排除；64历史失败、18历史未完成、11恢复保留。见[最终统计](reporting/summary.json)、[逐节点清单](reporting/coverage-manifest.json)及[12类问题](reporting/diagnostic-findings.json)。旧live文件与审查快照保留，不作为终态数量。

R371相关5项短回归均有本轮新通过记录，见[最终短回归核对](reporting/utc-short-regression.json)。完整UTC两后端外层合计4711.366秒，原合计600秒验收未满足；新场景前安装时钟偏移不等于同一活动任务中的真实宿主时钟跳变。当前脏工作区含未提交性能候选，不能归给干净HEAD或宣称受控性能改善。

当前54失败为标记关联36、范围集成8、资产1、T3五项、中文checker4项。真实Max、硬件、独立校准、合格B0、INITIAL/METHOD/FINAL及正式研究验收均不由软件诊断替代。完整raw/DB/资源侧车保持本地，精选证据不是完整远端复现包。全阶段总结见[R373最终报告](../round373-full-workflow-rerun-20261101/phase-summary.md)。
