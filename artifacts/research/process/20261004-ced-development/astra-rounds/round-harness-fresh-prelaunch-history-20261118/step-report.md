# 2026-11-18 首槽即时查重修复

GPT-6.2 Astra 制定、GPT-6.2 Sol 实施。实施前 12 项来源和原件 SHA256 全匹配。原始八根查重命中本批此前验证过的 `verification/dry-prepare/scene-assignment.json`。它是仓外安装准备流程的零模型 `PREPARED` 产物。原失败、准备归档和冻结回执完整保留。 [Astra 方案](plan.md) · [首次只读复核](review-red.log) · [输入 SHA](inputs-before.json)

即时查重只识别上述规范路径与 `cef1ca0bdac6ff21cc99325039eb090069e46b707d3b94f4598c4f9269c0381a` 同时匹配的准备文件，单独将其身份写入查重证据。相同字节位于其他路径、原路径字节篡改、其它同 seed 或同 pose 记录均保留拒绝。 [预期 RED](history-red.log) · [最终测试](history-green.log) · [JUnit](history-green.xml) · [Ruff](ruff.log)

最终 43 项测试通过。使用实际冻结检出、已安装 CLI、加密 profile 和首槽配置执行到即时查重回执前的只读边界。8 个根中的 321 份独立记录无冲突，文件指纹向量与初始准备一致，另记录唯一自有干跑登记。原冻结 SHA256 仍为 `41ae9cd2a411a1870b41f347c120371af67228dbe95facabecd21326308ca14e`。验证在开始回执创建前结束，0 槽开始、0 模型、0 云、0 实机。 [真实八根只读复核](eight-root-guard-check.json)
