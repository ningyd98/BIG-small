# R403：foreign-owner 目标前置失败的有界定位

实际 Astra 计划；仅诊断，不授权产品或测试修改。UTC：2026-11-02T16:37:25.681232+00:00。

原 R401 `fence_remaining_nodes_green` 为 1 failed / 4 passed；监督器 8.438308s，正常结束并清理。失败发生在 `captured(runtime)` 的初次 reserve 内，foreign thread 尚未创建。`_consume_transition` 汇总了 `_check_reference` 的非 VALID 判定；内部异常被转换为 UNKNOWN。现有栈不能确定时间耗尽、跨线程权限故障或 R399 SQLite 修复回归。CpuCounter 固定 0，不能仅凭错误文字增大预算。完整输入及 SHA256 见 input-audit.json。

允许新增小型只观察 pytest 插件及 R399 adapter 的显式 R403 stage overlay，一次原节点、原 fixture、原断言、新隔离输出目录运行。插件用当前测试线程 sys.settrace 记录有限异常/函数返回/verdict，不改函数、锁、时钟、异常或权限，不增加 DB/lease/clock 读取。精确 argv/env 与安全边界见 plan.json。先静态检查，后同原 supervisor 运行；不引入 helper smoke 或额外审查循环。

单次 60s + 清理 15s，计入持续的 R399 1800s；无重试或新 Git 配额。等待 R402/其它阶段终态并清理后串行运行。R402 原独立 native successor 可继续。源门保留原产品与 guard 模块 SHA，明确披露 R402 仅 native 身份属性修正。

如果原两个断言自然到达并通过、teardown/清理通过，独立终审可将此实例与原 memory、R401 sqlite、另外四实例按同产品/guard字节聚合；必须保留本次旧失败为未复现，不能声称已解释或修复。若仍失败/超时，guard 继续 BLOCKED，记录真正异常/判定原因，再由下一实际 Astra 计划决定修复；禁止以 native 成功豁免 guard。

仅精选本轮小计划、原 finding、审计、插件、运行/静态/步骤与解除记录进入原交付范围；DB/raw/副本及两 dirty gitlinks 不交付、不清理。保持开发软件、真实运行、正式研究边界。

启动补充：R235 前置须先以空 trace/profile hooks 通过；仅 pytest_runtest_call hookwrapper 开始本节点 call 时启用主线程 trace，finally 恢复。产品目录静态搜索未发现 gettrace/getprofile/settrace/setprofile 检查。记录器不得向产品帧抛异常；记录失败仅影响可观测性，不改变原执行结果。
