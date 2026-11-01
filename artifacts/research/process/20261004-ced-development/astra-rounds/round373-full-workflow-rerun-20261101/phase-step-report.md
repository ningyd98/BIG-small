# R373 全流程有界重跑步骤报告（诊断已结束）

用户要求“重跑全流程，继续总结问题”。实际gpt-6-astra制定[原计划](plan.md)，R374负责已确认运行前置与编排修正，R375负责最后的数据库作用域对照；产品/测试修复没有并入本轮。最终结论与4732节点终态见[阶段总结](phase-summary.md)，详细故障与原始证据SHA/调用索引见[findings.json](findings.json)。

## 执行与原始失败

收集4732个唯一Python节点、283个模块。先完成静态/前端/CED前置诊断，随后普通组01–04各在900秒上限停止；原通过数分别196、154、181、179，组04另有9失败，组02有2被选择排除。旧调用、stdout/stderr、pytest事件及退出回执均保留。

组05运行30.414秒后按R374身份核验方案中断，保留156通过、40失败、1个setup-only及492未轮到节点，没有补造result.json。中断及旧父进程回收见[R374停止回执](../round374-diagnostic-runtime-prerequisites-20261101/process/interruption-receipt.json)。

R374先完成T3九项（4通过5失败）与R223限定复验（9通过），再续跑尚未实际启动节点；新的独立错误仅记录，不重试或修改断言。两套continuation清单及原预算保留，v2只按Astra允许的范围调整未启动顺序。完整235子项最终全部记账，91启动、144预算未运行，已启动组均清理。随后R375唯一7项对照通过。

## 静态、前端和研究前置

Ruff格式135文件需调整；Ruff检查1137项/39文件；mypy539项/18文件。compileall、合同示例、pip check和模型凭据扫描通过。中文说明检查631文件，另4个checker测试失败。文档检查18次命中，原始含网络地址的扫描输出本地保留，提交派生脱敏分类。

前端43单测、两组类型检查、ESLint及构建通过；Prettier11文件未通过。默认浏览器40项为21通过、18未通过、1跳过，研究页面3项通过，见[R374浏览器账本](../round374-diagnostic-runtime-prerequisites-20261101/reporting/browser-results.json)。

CED selection/foundation记录NOT_EXECUTED，原因是未请求执行；power缺前置，未运行完整方法先导且assigned_denominator=null。INITIAL缺完整独立资源预算，退出3且未冻结。三个CLI的规划规模不应冒充真实研究执行分母。真实研究仍未验收。

## 验证、阶段报告与交付

本轮源清单1050文件无漂移，旧失败与冻结原件保持。阶段终态总计1845通过、54失败、17未完成、2743阶段停止前未轮到、71未运行、2排除。64历史失败与11恢复分别保留，不能称全流程通过。UTC长用例虽通过，合计4711.366秒仍不满足原600秒验收。

见[R374步骤报告](../round374-diagnostic-runtime-prerequisites-20261101/phase-step-report.md)、[R375步骤报告](../round375-diagnostic-database-scope-20261101/phase-step-report.md)、[阶段问题分析](issue-analysis.md)和[精选交付边界](delivery/BOUNDARY.md)。早先进行中的步骤报告已按原字节保存在R374/review/snapshots，原live覆盖快照继续本地保留，不用来替代最终统计。
