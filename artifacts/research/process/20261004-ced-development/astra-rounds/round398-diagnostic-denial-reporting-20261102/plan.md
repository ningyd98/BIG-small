# R398 — 拒绝分类不得被诊断日志解析抢占

实际模型：gpt-6-astra；仅静态修正计划。原 driver 27301 bytes / SHA256 `8a35abf5bfcf78bfde8aa1dd40d345fefcb5f7e955e5bbe1f4307809c8f267bb` 与完整 ready=false 审查已冻结在 inputs。完整审查 C0/I1/M0，唯一 R397-I1。精确 SHA 与规则见 input-audit.json / plan.json。

R397 已解决 child 拒绝后继续的问题。本次缺口是 supervisor 在读取 marker/exit78 前无保护解析 audit JSONL，随后 boundary、child-outcome、ready 及字段投影也可能抛错，使已知拒绝没有结果报告。这是报告路径问题，尚无行为运行。

只改 R396 diagnostic/diagnose.py 的报告处理：清理后先由 marker 存在、exit78 或已观察拒绝建立不可降级的拒绝状态；再逐行容错读取 audit/boundary，容错读取 marker/ready/child-outcome，检查消费字段的类型/缺失。保留所有原始字节和有效行，按文件/行记录读取、解码或结构错误；不把缺失日志当空成功，不宣称不完整 poll 列表是完整次数。

任何已知拒绝始终写 INFRA_BLOCKED_AUDIT_DENIAL / BLOCKED_BY_DIAGNOSTIC_POLICY，并返回非零，辅助报告错误不得覆盖它。无已知拒绝但记录损坏则标 INCOMPLETE_DIAGNOSTIC_OBSERVABILITY / UNKNOWN_OBSERVABILITY_INCOMPLETE，不能升级根因证明或软件通过。不得改 R397 强制退出、原 cleanup、产品、输入、mode、采样或配额；不得修改损坏原件或追加运行。

验收只用 AST 和静态数据流检查上述组合，不执行 reader/helper 或构造行为探针。独立 delta 审查绑定修后 SHA、解除 R397-I1 并确认 ready=true 后，允许更新 canonical R396 script-static-review.md/json；原 ready=false 继续保留于本轮 inputs。原 R396/R397 plan 不改写。

R396 one PCSC/one ETEAC、75秒及600秒 clock 未启动且不增加；一次 commit/push/exactverify 配额不变。精选交付只窄增本轮 plan.md/json、input-audit、original-finding、两个原审查小快照、step-report、review-resolution；重复 driver 快照和 raw/DB 留本地。
