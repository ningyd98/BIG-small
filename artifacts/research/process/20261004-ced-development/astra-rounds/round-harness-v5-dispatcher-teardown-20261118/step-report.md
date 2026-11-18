# v5 Dispatcher 停止观察与单次复验

冻结提交 `5103e7f483b9fccd40cf2e49d4bd5ef8979f64d2` 的 `suite-08` 有 724 个唯一节点，718 通过、5 跳过、1 项 teardown 错误。目标为 `test_batch_sweep_cancel_comparison_export_and_blocked_backend`。测试主体通过，原 fixture 在等待结束后仍观察到归属该测试的 dispatcher 活着。两份旧冻结组中同一节点通过，三个版本的测试、fixture 和 dispatcher 源码逐字节相同。原日志 SHA256 `369b8af76d2de772bac2774d47aa474d4a0c07445ed72d0ce8768fc462fa85b0`，原 JUnit SHA256 `60cc156c24e11fa0545ca7a91ab3e45ddd77a18ba8096fbc37a245049ce60cce`。[Astra 计划](plan.md) · [三份原件对照](comparison.json)

45 个计划输入执行前后均匹配。全部 CPU/EGL 分组和归档回放结束后，以原 CPU 亲和性 `[2,10]` 独占执行同一节点一次。保留原测试、原 2 s 停止等待和原 8 个 MOCK 作业。实际退出 0，外部 7.031 s。JUnit 记录 1 项通过、零失败和错误，6.251 s。原 fixture 返回后的旁路观察记录 teardown 通过、零存活 `simulation-dispatcher`。JUnit SHA256 `511910d128af9b2cfd078dcf3d307818fc8b7946fd0095663b7f59ecafeceee9`。

独立只读 SQLite 记录 2 个 MOCK 成功、6 个排队，另有 1 个 ISAAC 因环境阻塞。导出 CSV 共 21 行。复验的第二个 MOCK 作业耗时 1.318 s，启动早于导出文件落盘约 41.2 ms。原错误组的第二个 MOCK 作业耗时 2.840 s，启动晚于导出约 4.9 ms。两次的精确 stop 发起时刻未知，在途作业关闭的可靠性与调度归因仍待验证。SQLite 读回 SHA256 `84d1b6506894649128317f27945988309056174102240d125fd183997305ae47`。

原整库错误和单次独占通过分别保留。完整日志与回执位于候选工作树 `experiments/results/phase9/harness-candidate-validation-20261118/final/`。本轮无模型请求、无云调用、无硬件调度。
