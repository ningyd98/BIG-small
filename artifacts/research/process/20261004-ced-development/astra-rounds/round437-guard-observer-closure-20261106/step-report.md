# R437 步骤报告

15 项计划输入在实施前核对并冻结。新增三个反例，单次 RED 全部按预期在 call 断言阶段失败。限定修复包括：停止豁免收窄到当前线程的内部 CONTROL；observer/source 首个异常在安全检查点传播；诊断归并已记录的停止/快照 secondary，包括 overflow closure。无 guard 的观察器语义保持。

一次合并 GREEN：162 PASS、1 deselected，162 项 setup/call/teardown 均通过；一次 ruff/format/mypy 均通过。之后唯一实际诊断 1 PASS，真实 MuJoCo 两步，真实 BOOTTIME 到期拒绝命令及后续步进，安全停止完成，无额外步和附加错误。所有阶段源未漂移、子进程已回收。没有派第二 reviewer，三个 finding 的实施者修复核对见 review/fix-verification.md/json。

RED 后为显式绑定循环闭包变量调整了测试默认参数；implementation/red-source-reconstruction 保留按已知差异恢复的 RED 源字节，逐一匹配当时 runtime pins 的 SHA256 与长度，并明确标为事后恢复，不冒称当时冻结。

本轮不构成 full-H/native、完整抓放或正式研究验收。完整限制和主线后续见 R435 phase-summary.md；分层测试和源审计见 R435 test-report.md/json。
