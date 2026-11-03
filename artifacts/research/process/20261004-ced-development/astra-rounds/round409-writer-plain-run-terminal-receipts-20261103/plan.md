# R409：writer plain 验收与终态结果优先保存

实际 gpt-6-astra；UTC 2026-11-03T08:47:48.838493+00:00。R407 子进程已reap，但adapter先读缺失 stacks-observer.json，未保存真实returncode/result；旧code永久保持UNKNOWN，不能补造-11/-9或断言OOM/采样崩溃。原setupPASS、部分栈、空stdout/stderr与清理/源证据冻结。

新adapter仅行政补正：wait/poll取得真实exit立即写child-exit；owned cleanup后无条件先写不可变result（exit/state/cleanup/source），然后容错解析JUnit/events/prerequisite，另写stage-acceptance。缺失可选观察不能遮蔽原终态；必需call/teardown/JUnit缺失仍不验收，不能空列表all通过。旧adapter/plugin不改。

全新目录，原memory节点一次≤240s，15s清理；自然完整PASS才原SQL节点一次同限额。无额外faulthandler、trace/profile、Python采样线程或observerplugin，保留测试自有profile与所有原断言。父监督器可20s读取匹配owned PID/starttime的proc CPU/RSS和可读cgroup内存计数，不改限制、不发采样信号；缺失如实记录，-9或共享OOM计数不单独证明原因。

产品与测试字节不改，R40620GREEN保持。最多两次新行为、含清理510s，无全链30分钟钟；任何plain新失败/不完整退出即暂停下一节点，下一实际Astra计划，不重试。静态数据流/schema/argv验证后执行，无helper smoke或反复独审。

R408现仍BLOCKED。仅两R409 plain均真正验收且R408其余pins不变后，新回执可明确替代R408“R407两PASS”前置，保留R407失败/原R408计划；浏览器其余配置、工具审批、预算与次数全部不变。当前不运行浏览器/Git。最终一次whole-change独审覆盖全部历史边界，旧ready=false不回写。
