# 教师活性检查的 SQLite 单次读取优化

本目录原 step-report 与 checkpoint-timing 是只读定位证据。正式 v9 首动作在原 POST 以 STEP_TIMEOUT 停止，332.829s 对 8s。独立临时 SQLite 夹具在一次稳定检查中观测 13 个连接、26 次 PRAGMA、104 次 CREATE、8 次 INSERT、5 次 SELECT。40 次中位 5.747ms。共享连接、沿用原类型化读取的夹具为 1.045ms，p95 从 6.473ms 到 1.173ms；相同固定时刻的 lease 载荷完全相等。尚未据此证明并发等价或实际整段加速。原 v9 首组已消费，仍为 0/9。

## 修改与前置

1. 在教师的 NativeCollectionApplication.check_active 正常生产入口处理已初始化的真实 SQLite 运行库。只在每次调用的数据库读取部分使用原 publication_guard、同一数据库的新连接和一个只读事务快照。沿用原 job/lease/attempt 类型化解码和验证、查重、异常语义，以及控制器/worker 的取消、心跳失败标记、租约身份、尝试、fencing 与 original timeout 判断。可以复用既有谓词并增加极小的内部读取边界，优先保留原查询及顺序；不得把 SQLite 文本时区比较代替 _aware/UTC 解码或通过聚合/过滤隐藏重复、失效或非法行。记录启动时由同一受控运行库完成 schema 建立，若路径被替换、库未初始化/损坏或必要表缺失应从原可信入口重新核对或拒绝。快照不建立跨 checkpoint 缓存，不写权威状态。
2. 每次快照由原发布锁保护且同线程使用，读后关闭/回滚、异常也清理。与现有 writer transaction、线程局部 owner 和已嵌套调用保持原合同；不借用、伪造 writer capability 或自行改其连接设置。数据库访问结束即释放，不跨捕获、动作、控制器返回或其他等待持有连接/锁。现有其他仓储调用、Memory 后端、数据库建立/迁移和 worker 正常入口继续沿用原逻辑。作业身份、租约 CAS/heartbeat、取消、尝试读回、UTC 过期、单调钟与 OC1 deadline、OS 身份认证、RSS/物理步数、采样次数/触发位置、8 s Shield 均按原时机与谓词执行。
3. 列清实际取消、续租、租约替换/回收、尝试结束等写方与 publication guard 的关系，以确定快照的可见顺序。若有合法写方不共享该锁且原语义要求见它的提交，则保留必要的最后实时读或原路径，不把旧快照推成动作授权。只针对该读热点；命令历史复制/复杂度、PNG、OC1 优化、SQL schema 或采样频率不纳入此轮。

## RED、GREEN 与实测

- RED 在新 SQLite 夹具复现原 13 连接/重复 DDL，定向回归先证明原热路径未能满足新连接/DDL目标，另以原入口保存语义对照。比较相同时间及数据库内容的新旧 typed job、lease payload/来源摘要、异常类别和安全停机行为。覆盖正确/错误 worker、run/job、lease、attempt、空或重复记录、损坏时间/偏移、过期、task deadline、heartbeat failed、cancel_requested、发布失败与异常释放。交错操作采用两个独立仓储实例/线程与确定性 barrier，分别验证写方已提交、读期间写方等待、下次 checkpoint 立即见到取消/续租/旧 attempt 失效，不能混合新旧状态；测试真实模式的本地时间 authority 分支与嵌套 writer 行为。
- GREEN 从真实 check_active 入口测可观察 SQL 与连接数。稳定任务的数据库快照使用单个读取连接，初始化后其重复 DDL 和 schema 写入为零；如为已证明的并发语义保留额外读取，应列明条件和成本。对照运行原 worker owner、native collection authority、Phase11 SQLite runtime、操作时钟的相关测试与 Ruff/类型校验。以原计时夹具同机运行成对测量，记录 SQL 次数、中位、p95、样本数和环境；不能把某个绝对毫秒数设为容易抖动的单测门。若边界行为差异、互锁、不可接受延迟或原读/写鉴权改变，拒绝作为 teacher 运行候选。
- 通过后在新冻结源与新输出目录，用独占的小型零模型开发验证经过真实 check_active/owner/lease/取消路径；保留同密度、旧 wall guard 与物理安全，报告实际阶段耗时、控制与退出/物理原证据。可直接使用合适的较短教师开发片段，无须重跑已占首组；原正式失败、历史源码和回执原样保留。仍不足以满足 8s 时明确剩余实测成本与下一小项，任何新正式教师尝试另据真实资格与新分配。
