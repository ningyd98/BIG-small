# 教师诊断的两处原辅助调用兼容

两个原 authority 测试在新诊断实现上实测失败。_collection_guard 直接取旧辅助对象上不存在的 diagnostic，在退出时报 AttributeError；_close_body_resources 的 freeze 闭包在 recorder.freeze 前取同一属性，异常走次要失败路径并漏掉原 freeze。诊断新入口五项已过；旧失败日志含实际 argv 和源码清单。

仅在 _collection_guard 与 _close_body_resources 传可选的诊断状态参数，默认 None；从 run_from_worker 的真实 live/已绑定 diagnostic 明确传入。两个 helper 内仅使用该参数写诊断的 guard_exit 时刻和附加 payload。旧调用保持原 guard 退出、TERMINATION、freeze → detach → close 的顺序及初次/次要异常传递，真实诊断仍写原字段。不得只改旧 fixture 补属性、捕获异常吞掉、改单次语义或正式资格/控制程序。

核对旧失败、首个源码清单和测试原件，修前核对两个实际调用点。保留数据及旧回执，单独输出新结果。

原两个完整 node 与新增5项在真实模块复验通过，再跑受影响相邻集，核 freeze 一次、顺序及 dual-failure 次序；真实诊断写 guard_exit/payload，源码、测试与 Ruff 核验。无关旧静态基线逐项分列。所有适用原前置满足时即可按父轮在真实窗口执行一次。
