# R420 SQLite生命周期实施报告

实际Astra计划限定在adapter的_sqlite_summary及同一新测试。实现采用外层closing(sqlite3.connect(...))、内层原事务上下文，原SQL/checkpoint/VACUUM顺序不变。成功close后才计算DB hash；COUNT/VACUUM/末次checkpoint故障原sentinel透传，close恰一次。未改repository借用连接规则，不用GC、删除DB、释放强引用或进程退出替代显式关闭。

证据在R419/validation/r420-*。7个pre-fix case各一次：独立native返回前3FD为FAIL，4个summary生命周期断言FAIL，2个观察器控制PASS。7个post-fix全部PASS：强引用仍持有真实连接，正常和三异常均显式close；无替身native observer前后FD均空且DB hash在close后稳定；观察器正常/异常自身finally close。最终R419同新模块42PASS也覆盖这些case。

原red-native audit曾见4个本run FD，发生于adapter返回时、测试进程退出前，不是supervisor退出后残留；不能说4FD等于4个连接，未完成逐项归因。确认的是summary缺显式close及新scope资源关闭；旧原件保留。

重要口径修正：当时lease=0来自NULL-only观察器，而实际未释放值为空串，所以旧lease-clear结论撤回。R420 FD/close证据仍有效；R421修正谓词并释放自己的模拟旧lease后，最终scope正确计数0。Astra R420原计划保留规划时原文，不追改历史。正式研究资格没有恢复，范围不扩展到生产通用恢复。
