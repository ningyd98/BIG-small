# Phase 12 测试验收边界实施记录

基线 `41bb33344c0463a979327d0c78e2acd1088b458f`，测试变更提交 `8a6f7a8e9d2584267b8ab7b0e4167e648ec66ad8`。实际 [Astra 计划](plan.md) 的 56 项输入实施前 SHA256 一致。原失败、两份原始 summary 和所有运行资料保持；生产验证器、适配器、Mock/RGB-D 默认策略均未修改。

单项测试过去把 clean provenance 当成验收充分条件；18 条 F20 原件实际均未准入 RGB-D 执行器，证据缺口的报告是正确的。本轮让目标测试检查该场景的证据缺口，并增加三个 clean provenance 与独立证据缺口同时存在的拒绝对照；既有正对照和脏源码拒绝对照保留。

- 快速正反对照：5 通过，见 [JUnit](../../../20261117-grasp-lift-stop/evidence/phase12/controls-final.xml)。
- 原件断言重放：2 通过，未启动实验。原件真实提交字段为 `source_commit`：脏原件 `f258df862d96f25c2a0507f4b3b9f4f83049aa75`，干净原失败原件 `41bb33344c0463a979327d0c78e2acd1088b458f`。原重放记录误读字段 `git_commit` 为 null；[覆盖摘要](../../../20261117-grasp-lift-stop/regression-coverage-summary.json) 补充实际字段和绑定哈希，原记录保留。
- 新干净单项：1 通过，pytest 418.065 s。新产物仍为 GAP / NOT_READY / NOT_RUN；F20 18 条 BLOCKED_BY_ENV，未调用执行器，三个运行证据检查仍为 false。见 [命令回执](../../../20261117-grasp-lift-stop/evidence/phase12/single-command.json) 和 [产物复核](../../../20261117-grasp-lift-stop/evidence/phase12/single-proof.json)。

[独立复核](../../../20261117-grasp-lift-stop/phase12-independent-review.md) 验明旧 helper 仅目标测试调用，新增测试不影响共享夹具。覆盖总数按两种测试修订、同一生产源码去重；本步骤不授予 F20 或 full profile 正式验收。
