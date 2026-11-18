# Astra：UTC codec 性能窄修复计划

实际模型 `gpt-6-astra`，2026-11-18；**PLANNED_NOT_FIXED**。工作树、当前commit和全部输入SHA见 `plan.json`。此计划承接真实诊断，不声称修复已完成。与native视觉几何分轮处理。

## 原始失败与根因

原memory/sqlite两节点同进程合计600秒门在600.017148秒超时，均TIMEOUT_UNCOMPLETED。两个单独通过为2466.618/2468.269秒，不能代替原门。32秒CPU采样正常UTC shim为31.430CPU/31.843wall；移除shim仍31.448CPU/31.844wall。UTC时钟替身不是本次CPU卡点。

实际栈进入worker `_local_adopt/_local_mutate`，反复进行LocalEnvelope严格copy、canonical、semantic_projection、历史回放。route856395字节，裸解码1.018秒/profile2.075秒；supervision2465241字节，3.326/6.548秒。全帧profile约两倍代价不能单独解释约8.22倍总门缺口。保留诊断原件、采样SIGTERM/SIGKILL及首轮汇总失败；输入原始SHA绑定于JSON。

## 具体实施

1. 重核因果输入SHA，固定实际route/supervision/adoption内容及独立规范字节/hash。原600秒失败作为门RED；用真实decoder建立有限CPU对照，计数重复copy/投影/解析，不猴补验证成功。测试只针对实际重复工作和不变量，不能伪造一个更短任务替代门。
2. 首先仅改`vision/local_temporal.py`纯codec内部。优先在同一个已验证不可变`_json`对象的同步调用中使用一次局部解析/窄字段读取，避免getter→to_payload→_object重复整树复制；嵌套投影只在原根验证寿命内复用。所有外部新根仍严格校验，所有公开可变输出仍独立副本。禁止把外部输入当成可信字典、按id跳过验证、跨请求持久缓存、缓存授权/失败、以截断历史换速度。
3. 独立计量`_b_t2_observe`开销。可为UTC资源观察切换精确生命周期边界wrapper或code-local监控，保留真实poll进入/退出、session创建/关闭、thread启动、heartbeat、broker、issuer及资源清理证据。`wait_observer`或锁c_call注入依赖profile的相邻测试继续走原profile路径。不得只是关profile并删断言。共享观察器改动必须补startup/terminal/public回归。
4. 校对相同payload规范字节、digest、semantic_projection、返回类型、异常和所有授权/预算断言。分别测纯codec、观察器和整体收益，保留前后CPU与重复计数。不因微测快便宣称门通过。
5. 快测及相邻观察器回归通过后，原两个UTC node同一pytest invocation，一次合计外层monotonic600秒门；保留完整原断言、日志/JUnit/returncode/墙钟。原CPU7,15/线程1环境适用则保持；任何环境差异显式记载。保留faulthandler_timeout=0，不把原生watchdog崩溃再引入。

## 不可变边界

R315仍是128项/8MiB，完整canonical内容+精确class键、只缓存成功、每根清理、ContextVar token真实owner及copy_context/thread隔离。异常路径清理、超cap仍验证、同对象成功后修改必须再拒绝、不同class不串、负例不能负缓存。PENDING/COMPLETE、row revision、lease/owner/epoch不共享授权；当前authority/clock检查继续执行。

保留两次±24h、原local provenance和已耗预算、监督cadence、外部UTC±1/5秒精确边界、迟到硬上界拒绝、不再发布、资源关闭断言。TTL/任务期限/门600秒不改。不拆节点、不删case、不用并行独立长测替代。

## 范围与验收

允许codec、目标测试观察器、已有memo/copy测试和新增针对性能用例、派生诊断报告。worker_runtime/operational_lease仅输入证据，本轮先不改；若还需扩大同步操作缓存或修改worker，转下轮实际Astra。不得修改原始诊断或冻结原件。

验证包含完整route/supervision/历史promotion、篡改嵌套decision/transaction/reference/diagnostic、耗尽预算、输出修改隔离、同内容不同类、重复无效、cap溢出、copy_context和异常清理。具体节点见JSON。

预算0GPU/0模型API；每个限定CPU剖析进程≤60秒；修后原600秒联合门一次，无自动重试。只有原两节点在同次≤600秒全部通过才记软件门PASS，不授予真实模型/物理/正式研究/真机资格。计划外失败或门仍超时，暂停本项并回到实际Astra下一轮。
