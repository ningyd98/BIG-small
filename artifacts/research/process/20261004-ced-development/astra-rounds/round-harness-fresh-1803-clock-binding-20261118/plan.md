# 1803 归档时钟按实例化界分别绑定

原 Ruff B023 指向研究读回类 HistoricalClock.now 对循环局部 instant 的迟绑定，原 70 项通过，两端立即调用时已取得预期结果。只改 verify_fresh.py 这一小段。建议在每轮定义 HistoricalClock 时一次赋 recorded_instant = instant，在 now(cls, _timezone=None) 内返回 cls.recorded_instant；两个类各自保留其时刻、签名不变。允许按同义的每轮绑定作本轮机械 lint 迭代。保留原失败与原审计回执，复核 plan.json 的输入。按既有 70 项研究测试与 Ruff 验收，实际冻结构造器只读重建两端 0/30.199 ms、两次相同身份拒绝、原帧/距离/新派生1803结果等价。零 worker、零模型、零付费，不重复前三槽。
