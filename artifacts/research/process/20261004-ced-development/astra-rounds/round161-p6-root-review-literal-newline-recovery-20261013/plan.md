# R161：ROOT 有界文本读取的换行语法恢复

> 实际 Astra：gpt-6-astra（`/root/astra_status_plan`）。先经 ROOT 完整文本与 SHA 核对，再执行一次 reader。

原工具 5fed67 实际 exit 1：未完成的 Python `-c` 文本包含字面量反斜杠 n，解析即报 SyntaxError，发生在任何文件读取之前。原命令和完整实际工具返回已保留；独立 stdout/stderr 不可得，保持 null。这不是产品失败，R15815命令仍0已用。

本计划只恢复一次有界 stdlib 文本读取：operational_windows 590–675、worker_owner 60–105、owner registration fixture 38–65、verification_router 80–105，以及 memory.py 的 close 定义存在性和最多25行片段。合计最多600源码行，无 product import/AST/compile/subprocess/测试/静态/SQL/Git。完整直接 argv 位于 plan.json.reader，使用真实换行，不得再替换为字面量转义。

四个生产路径来自 R158 冻结清单。独立核查发现测试 test_visual_owner_registration.py 不在该清单；其精确路径来自原失败命令，本轮已只读确认存在并单独冻结 bytes/SHA，不修改 R158 清单或产品 scope。五个读取目标与两个元数据输入的完整 pins 均见 plan.json。

ROOT 执行前须全文读完整 reader 并固定其所在计划 SHA；唯一实际执行的完整结构化返回应立即 store，再保存本轮 actual-tool-return/step-report。未知分流保持 null，截断不得冒充完整读取。不得重跑原命令或扩大读取；新异常立即暂停相关 ROOT 工作。

Sol 独立 T1 测试和 runner 准备可以继续。ROOT 验证门仍 HELD，本轮成功仅恢复文本读取，不授予 B9 软件、native、实际、formal 或 Git 验收。
