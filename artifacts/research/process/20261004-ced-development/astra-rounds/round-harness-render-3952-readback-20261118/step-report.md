# 3952 独占复验回执只读重建

原独占 pytest 完成后，本地汇总器读取全局相机调整中的 `step_id`，抛出 `KeyError` 并退出 1。该调整使用观测标识和初始几何，无步骤编号。原 pytest 日志与 JUnit 记录 1 项通过、34.357 s。原子进程退出码和外层 monotonic 秒数未落盘，重建分别记录 `null`。

核对 49 个计划输入及原包装错误控制台摘要的 SHA256。以现存原件独立分类 4 条视角恢复、1 条 PLACE overview、1 条全局已注册视角，逐项读回 LIFT 替代观测、两段 RETREAT、末帧、物理评分与第 3952 步的三帧。两次只读重建逐字节一致，回执 SHA256 `626566e6aedb964a83cc7e49a354c9feb1523b7c2a0ec9117d6b26fedf0c8485`。本轮执行 0 项 pytest、0 个 worker、0 次模型请求。并行时限失败与独占通过按原运行分别保留。[Astra 计划](plan.md) · [原节点独占复验](../round-harness-render-3952-deadline-20261118/step-report.md)
