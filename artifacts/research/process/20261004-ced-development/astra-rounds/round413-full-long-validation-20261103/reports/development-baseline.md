# R413 研发基线与长测启动记录

此文件是启动阶段快照，不能代替最终测试报告。记录时间：2026-11-03T10:22:43.641261+00:00

被测分支 `research/20261004-continuation`，提交 `ab18abd0f82a024b62f4423c946c6585f8d18c65`。正式源码指纹 `3bfb7dbb8036b8389fa9a9bccdb2e961a1fd225be2d42b511539044e944995f4` 与 R412 一致。当前研发源无 tracked diff；历史 raw/untracked 和两处 dirty gitlinks 继续保留，因此不称全工作区干净。

| 范围 | 研发基线 | 本轮启动阶段验证 |
| --- | --- | --- |
| ETEAC 运行不结束 | SQLite 持锁内部调用改用对应私有 unlocked reader，保留对外锁、CAS、事务和预算约束 | 5 项真实 repository/native queue 回归通过；ETEAC 1.475 秒、PCSC 1.610 秒，各一次成功，租约释放且无心跳/运行 DB 句柄残留。MOCK 开发证据 |
| UTC 默认模式与权限 | 默认 UTC 模式进入原 typed validator，未知模式仍拒绝；owner/thread/source/clock 校验保留 | 4 项兼容回归通过；完整 UTC Memory 正在运行，SQLite 与其他 T3 尚待本轮结果 |
| 测试输入和版本登记 | 本轮重新采集当前文件，不使用旧4732清单或旧源快照 | 4753 个唯一节点、288 模块、采集错误0；4751 软件节点一对一分配，2 个真实数据节点 NOT_RUN_EXTERNAL_DATA |
| 浏览器和前端 | 使用现有依赖、当前断言，隔离输出、DB 与研究 fixture；不执行会改源的准备脚本 | 43 浏览器、unit/typecheck/build/API/static 已分配，当前尚未执行。R408 的42通过1跳过仅作为历史，不冒充本轮结果 |
| 全量实验 | Phase12 full 固定软件/仿真 adapter，外部模型/Isaac/ROS 环境不启用 | 环境前置为 CORE_READY；full run/analyze/export/verify 尚未执行，实际 BLOCKED/失败将保留 |
| 正式研究和硬件 | 沿用云、边、端既定计划和用户选定方案 | 本轮不是实体机器人或正式研究验收；不以单元测试、MOCK 或图像仿真代替真实证据 |

执行原则：仅运行一次；每个已启动节点不重跑。异常退出仅可启动事件账本明确未开始的尾部。测试断言失败继续独立组，不修产品、测试、阈值或原始字节。source drift、owned 进程无法清理或意外外部动作才暂停受影响部分。

历史未决项仍保留：R407 旧采样子进程的确切退出原因 UNKNOWN；R410 的40项既有 Ruff 告警只覆盖当时四文件，不表示本轮全范围 lint 结果；旧 UTC 两后端4711秒未达到原合计600秒性能门槛。当前原生测试回执仍有 R399 固定 `patched_worktree=true` 标签，本轮来源以实际 HEAD 与前后源 pin 为准，原回执不改写。

计划、覆盖分配和原始记录分别在同轮 `plan.md/json`、`assignment.json`、`implementation/<stage>/`；最终研发进展与测试报告在全部阶段结束后另行生成。
