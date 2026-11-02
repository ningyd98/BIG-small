# R397 — 诊断 audit 拒绝后的强制停止

实际模型：gpt-6-astra。只修 R396 driver 的运行前静态门，未执行诊断。输入字节与 SHA256 见 `input-audit.json`；精确条款见 `plan.json`。

完整独审仅有 Important R396-I1：audit_hook 虽阻止操作，却只计数、记录并抛 PermissionError。产品 broad except 可能吞掉它；driver 在 READY 和下一模式之前没有门，父进程只在终态汇总。这里没有实际网络逃逸或 ETEAC 动态证据。

限定只改 R396 `diagnostic/diagnose.py`：拒绝分支先置 sticky 标志，以固定路径独占创建首个 `audit-denied.json`、写少量非敏感事件/进程/模式信息，然后无条件 `finally: os._exit(78)`。记录失败也退出；不得返回产品、不得只依赖可捕获异常。父 supervisor 每个原 20ms 周期首先检查 marker，存在即使用既有 owned cleanup；部分或不可解析 marker 也停止。自然退出后仍检查专用退出码和拒绝日志。

child 在 imports 后、READY 前、每模式开始、poll 前后和成功结果前加防御门。任何 marker、退出码78或拒绝日志都优先分类为 `INFRA_BLOCKED_AUDIT_DENIAL`，结果返回非零，不进入 ETEAC 原根因判定。拒绝时强制退出会跳过 child/native finally，明确记录；不得从 monitor 关闭活跃 harness。禁止操作本身仍在 audit hook 中被拦截；这条基础设施停止不冒充原卡点或正常产品关闭。

不改产品函数、Lock、输入、mode 顺序、允许操作列表、采样或预算。修后仅 AST/静态数据流及独立 delta 审查；不执行 helper、人工 denial、smoke、锁探针、导入、SQL 或网络。独审必须绑定新 driver SHA、明确解除 R396-I1 并 ready=true，才可执行原 R396 唯一命令。

原 ready=false 审查及 driver 已冻结在本轮 inputs，不覆盖。只以窄附加项允许 R396 精选交付包含本轮 plan.md/json、original-finding.json、input-audit.json、step-report.md、review-resolution.json，以及两个原静态审查小快照；旧 driver 重复快照留本地。原 R396 one PCSC/one ETEAC、75秒、600秒、一次 commit/push/exact verify 不重置、不增额。
