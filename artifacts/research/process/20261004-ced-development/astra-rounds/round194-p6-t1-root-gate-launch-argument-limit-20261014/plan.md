# R194 — ROOT source gate 的参数传输处置

实际规划者 `/root/astra_status_plan`，实际模型 `gpt-6-astra`。仅规划；未执行恢复。

原工具在创建进程前返回 Argument list too long (os error 7)。无 process、numeric exit、chunk 或独立流；不是 Python exit1，更不是产品/测试失败。原件的 original_functions_return_preserved 只说明可见错误文本保留，不代表拿到了结构化 nested exec 返回。

实际保存 source 为101669字符、101697 UTF-8字节；命令为101725 UTF-8字节。重复内嵌原/终全文增大了载荷，但不据此推定具体 Linux 上限或探测阈值。已独立核对13个输入和状态：两角色四槽全部HELD0/1、gate.commands为空、source-review/release/prepare输出均不存在。源码与三脚本匹配 ROOT 给定完整 SHA。

限定恢复：ROOT 审核激活后，将原件 failed_metadata_code 原样安全保存为本轮新的文件，不改其检查、fullbefore、输出或角色逻辑；只可为 native保存补一个必要终LF并记录确切差异。不得重放原 giant command。ROOT 全文/哈希审核新文件和短 launcher 后，新增唯一一次120秒标准库 metadata action，以短文件引用运行它，独立保存 stdout/stderr/实际结果。具体 argv、有限环境、输入和输出绝对路径在 plan.json。

原25源码/211保护/插入diff/父账本历史/原raw等门全部保留。该新动作只完成原未执行的 source gate：创建ROOT文本审阅/prepare release，更新R192 gate和ROOT prepare reservation；author仍0/1、其它三槽HELD0/1。它绝不启动prepare、Ruff、pytest或settler。原R192四槽不重置、不增加；真实prepare须之后另由ROOT按原计划调度。

ROOT写前归档gate/ROOTledger并比较并发；源与三脚本不改，原失败不改。无新产品/静态/Git/网络/AST/导入预算。任何新的失败或部分写入如实保留并停止，不重试。本轮成功也只代表元数据门完成，T1/T12/native/formal均不晋升。

冻结 plan.md/json 后停止，等待 ROOT 完整审阅与激活。
