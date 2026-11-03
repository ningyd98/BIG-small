# R405 诊断结果

独立启动器从audit.inputs读取并核对82输入，真实原节点已运行：5.243秒、pytest1failed；R235通过、观察可用、无源漂移/信号/遗留、已reap。启动器字段问题已修正，旧R4030次子进程记录不变。

目标captured进入后，_check_reference在operational_windows.py:792抛unsupported live operational owner mode，实际mode=UTC_LEGACY_VETO（专用独立记录sequence134），随后返回UNKNOWN（135），_consume_transition在887拒绝（136）。146记录，异常0丢失、普通边界8丢失，关键原异常/结果链完整保留。没有创建被测foreign线程。

产品默认、原factory、clock、TTL、断言未改。根因是默认合法模式在引用检查分派中未接受；修复前guard仍BLOCKED。下一实际Astra计划后才修改产品。原30分钟关闭状态、全部失败和工作树锁修复保持。无实际硬件/模型，非正式研究验收。
