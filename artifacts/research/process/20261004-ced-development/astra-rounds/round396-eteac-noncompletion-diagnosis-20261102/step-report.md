# R396 步骤报告

实际 Astra 计划 → 精确原请求/35 pins 冻结 → R397/R398 两轮静态诊断门补正 → 独审 C0/I0/M0 放行 → 唯一真实 worker PCSC/ETEAC 复现 → 四组同线程同锁栈定位 → 自有进程按75秒 cap结束并reap。

PCSC SUCCEEDED；ETEAC 在普通 Lock 内再次获取自身同锁，H1_CONFIRMED_IN_CURRENT_REPLAY。超时检查位于同步调用前后，心跳独立，serial dispatcher解释后续排队。原R377栈未捕获，只能强支持历史共同根因。具体证据见 diagnostic/causal-report.md 与 causal-evidence.json。

源/原证据前后35 pins不变，产品未改，旧失败/raw/DB未清理。单次诊断81.622711040秒，forced SIGTERM为诊断取证，不是产品通过；实际运行/正式研究验收均未提升。

待独立最终审查后，只提交精确小文件清单；DB/WAL/SHM/完整raw/cache/tmp及重复driver快照留本地。提交推送配额各一次，600秒总预算不重置；后置Git回执留本地避免递归提交。
