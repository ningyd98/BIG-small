# 检查点诊断摘要的网络事件计数

公开附加摘要的交互式断言将 process-end.network_attempts 的 list 与整数 0 比较，观察到退出1和 AssertionError；事后文字转录 observed_terminal_only=true，保留其证据等级。两次正式的开发独立 reader 各退出0，字节相同 SHA 20d33461e7adf6d6770fd3f34a1297d62fb722142c1df3d814441dae96f3dcc8。正式资格 reader 则实际退出1，报 registered operational calibration protocol required。

原包装的 Python 审计钩子把命中的 socket 事件名追加到 attempted_network，再将列表原样写出。此次原件精确类型 list、内容 []；source_match 是布尔 true。

只准在新的离线摘要工具/派生文件正确取数。核 SHA 与 process-begin/end 同一进程，严格识别 JSON 数组并检查其中值符合已有审计事件；报告数组长度及事件口径，真实空数组产生0。缺字段/畸形拒绝，有事件作为非零保留并拒绝“零事件”判断。不得把缺失/null/false/0/空字符串当空数组。来源保护、正式拒绝、原正式 reader、诊断 producer、claim 和实测原件全部沿用。

原始失败仅留交互式错误观察；固定原始输入，另路径产生派生。零模型/零EGL/零设备，不调用采集入口。

实件得到0个 Python 审计钩子命中的网络事件，另列 requested_task_model_calls=0 和正式资格 false。两次独立小摘要逐字节一致，旧开发 reader 两份相等、退出0、正式 reader 退出1和错误消息按原件引用。小反控覆盖合法非空事件、非数组/缺字段，防止将错型等价为零。按原证据记账，不将进程内审计推断为系统范围的网络证明。

逐件 SHA256 见 [plan.json](plan.json)。
