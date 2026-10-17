# Astra Round89：激活收据紧凑派生表示

规划 gpt-6-astra；ROOT实施，Sol重新pin后继续R87。状态PLAN_ONLY。本轮仅元数据体积问题，不是产品/测试失败，不改R87计划或82+7发布范围。

## 发现与输入

真实原发现见 `t12-sol-handoff-20261007/delivery-p2/activation-size-observation.json`，SHA256 `48cda9be1bea36ba26387ded27073611a3bc9c1636c0df6b1dc85c6431b2728b`。Sol暂停copy/stage/test，candidate4=0。ROOT原激活脚本exit0，14项输入和82项候选已核验；父98b8282138ba61367db526d7d8f52e27085f4f9f及三SHA/clean是原运行证据，不重述为本轮新Git检查。

本代理读原激活与实际脚本确认：root-activation.json为10005801 bytes，SHA256 `39376d5386e9944b6fcf3e737b65862887659514e9698b5fecb217d95a7b8e74`。两份嵌套status分别同时存于nested_workspaces_preserved及commands[9]/[10].stdout，原脚本return .strip()导致两种保存字符串略有不同，必须分别hash而不能共用一个摘要。实际脚本/tmp/bigsmall-r88-activate.py为5099 bytes，SHA256 `2d77c902c010187d63ee4211117d56b22ef61bd4afcd5f176bbf4519755cd394`。原激活、脚本、R87两计划与真实发现的5项pins见plan.json；本轮不复制或更改它们。

## 限定实施

1. ROOT写入前复核5项pins。把原激活完整10005801字节复制至本R89目录 `original/root-activation.verbatim.json`，使用新建不可覆盖语义，逐字节/bytes/SHA验证与原文件相同。完整原件local-only，不stage、不删减或改原始JSON字节；备份验证成功前不得替换原路径。原发现和脚本也保持不变。
2. 从原字节解析对象，仅派生替换四个文本字段：nested_workspaces_preserved[0/1].status与commands[9/10].stdout。每个值改成明确摘要对象，含representation=STORED_UTF8_TEXT_DIGEST、UTF-8编码后的sha256/bytes、nonempty、原命令exit_code，以及原件SHA/bytes和对应JSON Pointer引用。保留nested path、全部commands argv/cwd/exit_code/stderr。摘要描述的是原JSON保存的字符串，不冒称解码前进程管道原始字节。两status与各自stdout.strip()关系核对成立；各自字节/hash分别记录。
3. 顶层只新增 `receipt_representation=DERIVED_COMPACT_RECEIPT`、`derived_from`（原件local-only路径、SHA、bytes、原time_utc）、`derivation`（R89 plan SHA、派生时间、上述四个JSON Pointer、no_git_rerun=true）。原status和time_utc保留，不能把派生时间当新Git观测。其他全部原字段逐项深度相等，包括原Git证据、14+82计数、五源、收据/pins、父级、三SHA/clean、candidate4预算及出版边界。
4. 序列化到同目录全新临时文件，验证合法JSON、四摘要可由local-only原件重算、仅允许字段变化、原备份hash保持、compact大小小于65536 bytes。验证失败保留新文件和错误，不递归删字段或重跑Git；回Astra。通过后一次原子替换R87/root-activation.json，形成原样原件与紧凑派生件两个明确版本，不改R87 plan.md/json或原82载荷。
5. 保存小型本地派生步骤收据（旧/新SHA/bytes、四字段映射、结构不变量、原件保留路径），不触发任何Git/产品/pytest/mypy/status重跑。Sol重新读取并固定compact activation的实际新SHA，核对derived来源后再继续原R87的候选准备/一次candidate4。先前没有以大激活冻结发布清单，因此无需篡改旧提交或伪造旧pin通过；若实际出现已冻结引用，保留并显式重新登记新版本。

## 验收与边界

原10MB完整字节可本地复核；compact四字段摘要准确，其余旧证据不变且明确为派生；R87发布仍82载荷+7固定元数据，compact替代同一个activation路径。R89计划、原件、发现/派生收据全local-only，不扩发布范围。不得重跑百万路径nested status，不清理嵌套树、不改用户1007、产品或raw/DB。

本轮actual/test/Git调用均0，candidate4预算不消费，formal=false。保持旧证据时间属性；后续ROOT最终commit/push仍按R87核验当时三SHA，不把本派生收据冒称新的远端验证。
