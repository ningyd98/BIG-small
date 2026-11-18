# 2026-11-18 标记开发注册 v5

GPT-6.2 Astra 制定、GPT-6.2 Sol 实施。父冻结 `02dbaef9` 原 suite-01 的 725 项结果为 680 项通过、45 项失败。45 项均由 v4 生产加载器在检测器源文件漂移后拒绝。实施前 26 个输入的 SHA256 全匹配，原始报告和清单保留。 [方案](plan.md) · [首跑失败索引](failure-evidence.json) · [输入复核](verified-inputs.json)

新增 v5 开发登记，固定 SHA256 `64d111c52a08636ee9b3cdae9f874d4a932ed98d357be7cde501279d088216e9`。相对 v4 唯一变化是版本化登记 ID 和 `pose_markers.py` 的真实源 SHA。保留资产、几何、其余五个绑定及 `DEVELOPMENT_ONLY`。两个显式当前测试消费者选用 v5，已有运行时、脚本和 v1–v4 登记均保留原配置。候选新增受控产品路径仅为 v5 YAML。当前生产源码相对父冻结 `02dbaef9` 无变化，和更早的 `980c66e9` 仅有已单列的 Phase 11 签名兼容补丁差异。 [验证回执](verification-receipt.json)

当前 v5 真实加载通过，当前 v4 仍按原绑定规则拒绝，双向错误注册摘要均拒绝。历史检出 `3ca2f641` 的 v4 文件、六项源与资产逐一按该提交原字节核对，再通过该检出的真实加载器。本轮保留 v3→v4 测试身份，历史证据由独立只读运行完成。 [预期 RED](focused-red.log) · [历史正例](historical-v4-verification.json) · [最终焦点](../round-harness-marker-registration-v5-format-20261118/focused.log)

在 `5103e7f483b9fccd40cf2e49d4bd5ef8979f64d2` 冻结的两个模块合计 59 项通过。相同冻结版的 suite-01 实跑 728 项全部通过，JUnit 与结果清单覆盖原 725 个和新增 3 个节点，原 45 个失败节点均按原身份通过。归档诊断相关 144 项通过，旧四例的数值报告按候选重跑后 SHA 与先前完全一致。 [节点映射](node-mapping.json) · [新冻结版 suite-01 复核](suite-01-verification.json) · [归档焦点回归](archive-focus.log)

本轮模型、生成、云和实机均零调用。四槽旧冻结与预登记原件保留。重新冻结和同版本运行等待独立 Astra 轮及其放行，正式资格保持 `NOT_ACCEPTED`。
