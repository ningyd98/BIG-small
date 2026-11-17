# 仿真基线回归实施记录

按实际 Astra 的 [计划](plan.md) 和 [输入清单](plan.json) 实施；44 项原始输入与 Git 对象验证一致。[历史失败](input-evidence/) 保留原字节。源码提交 `41bb33344c0463a979327d0c78e2acd1088b458f`。

三项基线修改都只涉及测试。固定历史 finger 核验用 Git 兼容快照作正例，原 52df pin 和真实当前树拒绝保持；seed 43001 在真实 MuJoCo 软件 worker、一次云替身请求、新帧复核及最终准入后成功，保留 REOBSERVE 和遮挡拒绝；批次归属测试继续真实写读 API 和 SQLite，只在该项停用无关后台领取。冻结验证、批次及云候选相关测试分别取得 46 和 223 项通过的分组结果。

原闭环九项的七项长测试在历史每节点 600 s 上限内通过。两项 UTC 完整独立诊断同时关闭开发缺口；原双后端合计 600 s 验收仍超时并单独追踪。原始分组用原生 pytest 输出逐节点 JUnit。分组首次 56 个失败中，55 个由不符合既有权限或归档根要求的临时目录触发；使用独立 `/tmp` 在同一源码条件下复跑通过，没有改生产安全规则。剩余 Phase 12 的测试契约在[单独轮次](../round-phase12-clean-provenance-gap-20261117/step-report.md)关闭。

[阶段总结](../../../20261117-grasp-lift-stop/report.md) · [覆盖摘要](../../../20261117-grasp-lift-stop/regression-coverage-summary.json) · [闭环原始 JUnit 与回执](../../../20261117-grasp-lift-stop/evidence/closure/)
