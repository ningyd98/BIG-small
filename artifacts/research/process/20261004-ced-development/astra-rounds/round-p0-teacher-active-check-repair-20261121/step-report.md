# 教师活动检查的重复读取修复

按 gpt-6-astra 的限定计划，在教师 worker 的轮询期间复用线程与进程绑定的只读连接。每个检查点重新开始、结束只读事务，并在事务前后核对数据库身份。同一个事务中，同一作业的三个读取复用首条原始行，各次返回新构造的记录。应用从注册时的冻结协议取得 RSS 和物理步数限额，对改变的协议沿用重新解析路径。 [修复计划](plan.md)

在运行中软件 worker 与真实 SQLite 上，交替运行的单次检查中位数由 2.22–2.27 毫秒降至 1.36–1.41 毫秒。故障注入覆盖同一步的跨进程取消、租约自然到期或替换、RSS、硬时限、急停，以及数据库 inode 替换、事务异常与线程和进程隔离。新增 15 个独立用例与既有 authority 用例合计 51 个通过。独立基线先断言实际导入的冻结源，再记录原有控制与新增接口的预期失败。 [独立软件复验](independent-equivalence-and-timing.md) · [计数和时间](../round-p0-teacher-active-checks-20261121/software-check-active-pairs.jsonl)

邻接回归中发现一个教师测试桩因缺少现有关键字参数而提前退出。独立修复轮恢复了原来要检验的源漂移错误，六文件回归 294 通过、19 跳过。交付前，含仓库治理及新读回器的八文件复核为 157 通过、19 跳过。两套回归有重叠，用例数分别统计。 [夹具修复与回归](../round-p0-teacher-state-source-guard-fixture-20261121/step-report.md) · [复核回执](../round-p0-teacher-active-checks-20261121/retention.json)

同位姿 MuJoCo/EGL 开发复测保留了 31,238 次检查。检查及其 SQLite 读取少用 27.947 秒，首动作整体少用 21.665 秒。原 8 秒门限仍在 POST 拒绝。 [首动作复测](../round-p0-teacher-active-checks-20261121/step-report.md)
