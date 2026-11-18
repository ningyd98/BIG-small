# v5 测试持有的 dispatcher 未在原 2 秒内停止

目标节点是 tests/test_phase11_simulation_workbench_backend.py::test_batch_sweep_cancel_comparison_export_and_blocked_backend。suite-08 原 724 个独立节点为 718 通过、5 跳过、1 teardown ERROR。stdout 的 719 个 PASSED 包含该节点已通过的 test body，JUnit 将它归为单一 ERROR。5103e7f4 的原组退出 1。原测试、fixture、dispatcher、worker 与 v5 的运行时并未因 marker 注册变化。保留全部原件、原两次通过与新失败。节点时长依次为 5.229、5.163、6.972 秒，后两版均 pin 核 [2,10]；此前初版 [3,11]。没有同瞬线程堆栈、精确 stop 发起时刻或可把失败归为主机争用的测量。

原测试通过真实 API 提交 8 个 MOCK 作业，比较和导出在作业可仍排队时返回。SQLite 最终状态前两次均 MOCK 成功 1、排队 7；本次成功 2、排队 6，三次均另有预期的 ISAAC BLOCKED_BY_ENV。第二个 MOCK 在 v5 于 UTC 14:26:02.661456 开始，14:26:05.501395 完成（2.839939 s）；导出 CSV mtime 为 14:26:02.656580，相差约 4.9 ms，文件 mtime 不能替代测试 teardown 时间。tests/conftest.py 按对象/线程归属调用原 stop 后检查 is_alive；dispatcher.stop 设置事件并 join(timeout=2.0)，循环中同步执行 worker.poll_once，停信号在外层循环边界查看。这构成在途作业与停止窗口重叠的具体假设。现有原件证实线程检查未通过，但无法定位原线程正执行的函数或证明 CPU 调度为根因。

本轮仅诊断及同版独立验收。Sol 先核 plan.json 输入及原件只读 SHA，保存 JUnit 所属、原组/旧组与本地 SQLite 来源。待 v5 剩余并行负载、正在使用共享时限资源的验证和独占回放自然释放，在 /tmp/bigsmall-harness-v5-verified-20261118 的同一 5103e7f4 原环境、原线程限制及 [2,10] 亲和性，单新目录/原 timeout 只执行这个测试一次。保持真正的 TestClient、SQLite、原 8 任务及原 fixture，零真实模型、云、真机，避开正式四槽。记录实际时刻、命令、进程退出码、JUnit、源及试次前/后系统负载。可使用旁路 pytest teardown report hook，只在 fixture 已执行完后读取现存线程栈（方法名/行号、线程 ident、归属 tmp 路径，避免局部变量和敏感数据）；不得改变生产 poll/stop、延长 join、延时测试体、引入额外的线程调度门或清空队列。钉住原始报告，只有报告已返回后再只读核对数据库/产物、剩余队列、是否有同测试拥有的存活线程；捕获不到堆栈或时刻应如实留空。

单次独立通过且原 fixture 正常清除自己线程，即报告一次当前版原节点验证通过和整组首次 ERROR 两项。不能把它变成初次全绿、证明可靠关闭在途作业或给出调度根因。若仍有 ERROR 或确有可复现的生命周期错误，保留原线程栈、作业状态/归属、原退出码和时限，停止依赖放行，由 Astra 制定具体生命周期修复方案；此轮不改源码、断言、授权、取消策略或数据库，也不授权第二次试跑。软件结果、真实四槽、正式资格分别记录。
