# Astra：归档延迟的有限诊断与独立验证

实际 `gpt-6-astra`，2026-11-18，PLANNED_NOT_RUN；输入SHA见JSON。当前两项相机绑定Important已独立闭合，235 CPU及10真实帧/5游标反例通过。但唯一postguard完整回放在LIFT2480按原100ms TTL正确STOP，worker及物理失败，必须保留。

坏帧captured 00:57:28.132878Z；depth mtime +10.278ms，mask +122.014ms，observation +122.819ms，两写入时间戳间约111.737ms；前样本归档13.011ms。此前sample+IK最大50.652ms，2480只有双hold/estop。相同物理步像素/深度/mask/calibration与旧成功一致。mtime并非系统调用耗时，原TTL检查时钟未记录；不能断言磁盘、新守卫或某个Python步骤是根因。

本轮**不改源码、测试或控制策略**。先冻结当前source/test SHA与预算，原全部反例证据仍适用则不重复整套测试。一次只读环境快照采集UTC/monotonic、挂载与空间/inode、load/pressure/IO与CPU计数、可得的进程/限流信息、GPU占用，缺项如实记录；不装工具、不杀他人进程、不改调度/缓存/挂载。

允许一次同文件系统小量探查：最多8个已归档帧、32次原文件写入、16MiB、30s，按原save_servo_frame顺序在新目录写，每帧仅一次。记录各写入与归档起止monotonic/CPUtime及操作间隙。任何归档>100ms或错误即暂停完整验证，提交证据交下一Astra；不得重复探查筛选快的一次。

诊断launcher可仅对新servo-frame路径包装原归档/Path写入及必要的验证入口，原样委托原函数、参数、返回与异常，不改字节或次序。只在内存缓冲有界计时记录（≤40000事件/16MiB），结束/失败后落盘。可被动注册gc.callbacks记录start/stop、generation与计时/计数，关联wall/thread_cpu/process_cpu和前后Dirty/Writeback/pressure；不禁用/调GC、不强制collect。最多256次无IO计时缓冲微调用（<1s）估计诊断开销，仅报告、不从期限扣除。禁止预先sync/fsync冲刷来改善环境。记录实际写入耗时和写入之间的空档；不作全帧profiler、同步日志洪泛、异步归档或扣除测量开销。包装开销仍计入原100ms；小量探查同时核对字节一致与异常传播。

预检通过后预登记**唯一1次**新独立完整零API验证：新目录，原共享GPU锁独占、无并行renderer/compute、EGL、原协议与模型/网络阻断、worker120s及外层900s不变。无额外GPU预热/重建/RED，不重试直到通过。逐样本保存归档/校验monotonic轨迹与原sample+IK；再次TTL或任何失败立即停，不跑余真实seed。

若唯一新验证全GREEN，需原8技能/9段、最终安全退避及终帧效果、worker完成与独立物理成功、全部绑定/2mm/max2/100ms/安全门均成立，才按前计划放行44102..44104。已花4cloud16local、余3/12、总cap7/28不变。fixed02/03不重跑，44101 SAFE FAIL永久保留且不优化。所有旧失败/成功及源码版本分列；新验证若启动即分母1。单次通过不能证明硬实时，也不能倒推出旧延迟根因。formal NOT_ACCEPTED、qualified_groups_added0、真机NOT_STARTED。
