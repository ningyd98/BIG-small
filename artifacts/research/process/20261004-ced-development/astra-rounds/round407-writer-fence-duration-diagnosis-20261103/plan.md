# R407：writer guard 分段耗时诊断与补验收

实际 gpt-6-astra；UTC 2026-11-03T08:40:41.343487+00:00。本轮仅在 R406 三组 GREEN 全部自然通过、源与清理门完成后执行。规划不读取尚在增长的 R406 结果；终态后另生成带 SHA 的 gate 回执，不刷新原件。输入见 input-audit.json。

旧 memory138.021s、SQL139.94s 均实际 PASS；180s 合并 cap 不足容纳两个串行约140s 节点，并非用户产品 SLO。既有栈在 JSON/local_temporal 真实语义路径；测试还对完整 writer 清单反复做事件/作业快照与序列化，原因需多时点证据，不先优化产品。

使用新 R407 adapter，原两个参数节点分别一次≤240s，各15s owned cleanup，依次 memory、sqlite；总运行清理上界510s，不设新的全链30分钟截止。产品、测试、snapshot 和断言全部不改。新目录/DB、原 R235/R373/env/marker、源快照和 owned supervisor 原保护保留。

本测试自己安装 sys/threading profile。禁止 cProfile、覆盖/链式修改 profile、trace 或新 Python sampler线程。小插件只在 R235 后 test-call 内启用 faulthandler 原生20s重复全线程栈，finally取消并关闭；不同时传 pytest faulthandler_timeout，避免共享定时器冲突。可在父监督器同20s间隔读 /proc 子进程CPU/RSS计数，非行为探针。样本只支持定性分类，不能当精确耗时占比。

真实 PASS 须原call/teardown、writer拒绝/负取消与cleanup断言完整。两节点通过可补当前源码的软件guard证据；旧180s失败仍保留。如只是串行耗时大于旧行政cap，记录分段预算合理，不宣称产品性能修复。新失败或未知卡点则下一实际Astra计划，不重试/扩scope。浏览器和最终精选Git交付另具体计划；本轮不运行，不改dirtygitlinks。最终whole-change独审合并R405/406/407，不追加helper反复独审。

落盘前终态补充：R406 三 GREEN 已全部结束，result清理/源门静态核对通过；最终结果/JUnit/events/source/cleanup/prerequisite及总结均补入输入审计SHA。执行前仍须完成明确的终态适用回执。旧ready=false不回写。
