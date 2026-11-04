# R431 原件联接与字段语义

按实际 Astra 计划修复 F1 COMMAND/CAPTURE 穷尽联接、F2 同域 clock tee 和父子区间约束、F3 动作及 RawV3 严格字段语义。新建7个反例及完整正例：RED 7预期失败、1通过；GREEN 91项 setup/call/teardown全部通过，无跳过、source drift或存活子进程。

Ruff与格式通过；mypy变量复用3条错误转交实际Astra R432并完成限定等价修复。独立Astra审查确认原F1—F3闭合，另发现F4畸形前置action造成后续合法失败原件遗漏，保持INCOMPLETE但证据不全，转交R433。此报告不将该残留提前关闭。

COMMAND原始结果包含physics_state及command_records，样例已按真实源码布局修正；未运行真实COMMAND或完整H生产端。完整临时文件保存在本轮implementation/post-run-fixture-originals，仅本地，不纳入Git；派生清单不是完整远端复现包。
