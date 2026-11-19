# 教师采集辅助调用兼容修复

新增诊断入口的相邻回归最初为 84 通过、2 失败。原 `test_guard_normal_exit_has_termination_parent` 在 guard 退出时因旧调用对象缺少新字段异常。原 `test_collection_cleanup_failures_preserve_all_and_close_once` 在 freeze 闭包遇到同一属性错误，只执行了后续 detach、capture 和 backend 清退。两条失败使用真实代码复验并封存原日志，SHA256 `bccd65edb460272ad1a083c9a44a28f305ad693edbfe997f45fa99b0ed59b45e`，里面记录了确切 argv。 [Astra 窄轮计划](plan.md) [失败证据清单](../round-p0-teacher-checkpoint-egl-development-20261120/execution-summary.json)

计划的 7 件输入全部核对。修复为两个辅助函数提供显式的可选 `diagnostic` 参数，由正常 worker body 在有登记时传入。原调用和现场测试保持原接口。原 2 项、诊断新增 5 项一并通过，随后相邻实跑 86 项通过，其中一项既有依赖弃用警告。真实 EGL 原件也记录了 guard 退出时间、新诊断 payload、一次 recorder freeze 和全部清退。 [本轮验证与实际结果 SHA256](../round-p0-teacher-checkpoint-egl-development-20261120/execution-summary.json)
