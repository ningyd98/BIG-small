# R405：独立观察启动器与 owner 前置失败定位

实际 gpt-6-astra；UTC 2026-11-03T08:28:16.011790+00:00。用户续授权“按顺序继续修复（诊断启动器→权限前置失败→补齐验收→浏览器复测与精选提交推送）”。本轮仅实现独立诊断启动器并运行一次原 foreign-owner 节点，不预授权未知根因修复。

R399 已关闭：核心锁修复及 ETEAC→PCSC 原生成功有证据，guard 未完成，ready_for_delivery=false、未提交推送；1800s 旧预算超限的事实不改写。R403 启动前 schema KeyError，原目录仅8个普通目录、0文件，实际子进程0；R404 未实施。R405 使用全新目录、全新单次配额和时钟，不能复用或刷新旧阶段。

输入 SHA256 在 input-audit.json 的唯一 `inputs` 列表。当前产品 `7d73669b…`、native 测试 `1e74f8c3…` 固定。原 adapter/plugin 已按字节保存为本轮 local-only 输入副本。保留两 dirty gitlinks，不访问内部。

实施顺序：

1. 从冻结 R399 adapter 派生独立 R405 adapter，仅加载本轮 plan/audit.inputs；保留源快照、原 R235 前置、显式 env/marker、owned subprocess 与清理。去掉旧阶段执行和旧预算引用；新增目录必须不存在。
2. 从 R403 观察器派生小插件。R235 空 hooks 前置后才在原节点 call 启主线程 trace；捕获目标 captured 进入之后的异常/少量边界与 verdict，避免启动期/递归描述事件耗尽容量。EvidenceVerdict 是非 slots dataclass，status/reasons 可从普通 __dict__ 读取。所有观察不得改变产品异常、锁、clock、TTL 或断言。
3. 纯静态 AST/数据 schema/命令/env/path 验证，冻结派生文件 SHA；无 helper smoke、无产品 import、无额外实施前审查循环。
4. 一次原节点，60s child + 15s owned cleanup，精确 argv/env 见 plan.json。独立记录本轮时间；报告和独审不挤入旧1800s 或新的人为30分钟总钟。只一个行为配额，无重试。
5. 保留原始日志/异常/verdict、source-before/after、prerequisite、JUnit/events 与清理，形成因果报告并独立证据审查。

原 CpuCounter 恒0，现有外层错误并未证明时间耗尽；描述域/身份校验、原源/owner/UTClease 与实际 operational verdict 均待真实记录区分。失败时 guard 仍 BLOCKED；诊断得到明确根因后下一实际 Astra 计划再修。自然通过只有在原两个断言、call/teardown、源门/清理/观察均完整时可补实例验收，不能说旧失败原因已修。

后续慢测、浏览器与交付保持用户顺序，但本轮不启动：先基于确定根因规划修复和必要验证，再给浏览器具体输入/argv/服务就绪/预算与清理，最后独审明确文件清单后普通提交推送并核对三SHA。不得将 native 成功换算为19个历史browser失败关闭，也不得把软件结果升级为硬件或正式研究验收。

补充强假设：software_factory 未显式传 mode，worker 默认 UTC_LEGACY_VETO，而 _check_reference 仅接受另外两种模式。必须独立保留该 unsupported-mode 异常（若真实发生）、现有 mode 局部值与后续 UNKNOWN，不受256条环形记录挤出；严禁先改 mode。此时仍为静态假设，真实诊断后下一轮再决定兼容修复。
