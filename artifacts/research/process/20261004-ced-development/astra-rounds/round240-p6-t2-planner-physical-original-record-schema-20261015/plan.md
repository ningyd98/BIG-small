# R240：规划输入历史归档结构处置

实际作者：gpt-6-astra（/root/astra_status_plan）。仅冻结计划，纠正核验尚未执行。

原 e42fa3 实际 exit 1：规划器把 `physical_original` 对象传给 Path，发生 TypeError；聚合没有打印。完整失败原件 2903 bytes，SHA256 `621b7b96e405af91dfaa50b33657a921b601c6f00a8e29bcbdfc01f46fc91977`，保持原字节。没有产品或测试执行，没有源码变更。

实际27项都采用 `{original, archive, mode}`，original/archive各含path、bytes、sha256。当前 row/base64 与历史归档分代：runtime当前123955/9b94…，归档为112914/2dcd…；不能把它们硬比。其余字段保留，文件身份仅比较三字段。

ROOT完整审阅 plan.json 的十项输入、实际schema及完整核验源码/argv后，才可放行一次120秒标准库元数据核验。它逐项核27当前源/base64、27历史原件→物理归档以及211保护文件；新报告独占写入，stdout≤6000字节。原错误命令不重放，没有替代产品执行、测试、SQL、Git或审查额度。任何新失败保存原始返回并停止。

实际返回必须先store再显示；未知独立stdout/stderr记null。成功只恢复R239规划资格。ROOT已完成R237/R238结算，最终角色、结算原件和STATE/PHASE时间点已实际取pin；六新DB及十八sidecar状态由完整结算authority绑定，本轮不读取数据库。状态与角色只作当前适用性输入，后续合法变化须完整归档/CAS，不当永久不变量。R239旁观诊断没有因此获执行许可；旧三槽均spent，不重置，T2未完成。

完整输入SHA、逐项核验算法、独立一次槽、输出及前置条件以同目录plan.json为准。原计划、原失败、旧索引和全部源码不改。
