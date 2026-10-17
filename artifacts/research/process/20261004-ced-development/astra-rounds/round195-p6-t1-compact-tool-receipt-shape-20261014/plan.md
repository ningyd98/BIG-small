# R195 — compact child 回执与完整结果的元数据合同

实际规划者 `/root/astra_status_plan`；实际模型 `gpt-6-astra`。这是预执行静态问题，ROOT settler 与 GREEN51 都未执行，不存在本轮 pytest/settlement 失败。

独立核实12组回执：五份 metadata preparation 的 actual_summary 与完整 result 相等；六份历史 child 加新 Ruff 的 compact summary 每个现有字段均等于其独立 pin 的完整 result，whole equality 按设计为 false。当前 actual_tool 的无条件全等断言不适用 child。236项当前源码/保护匹配；prepare/Ruff已花费且ROOT接受，最后两槽仍HELD0/1。

仅 ROOT 自有 root-settlement.py 的 actual_tool 与 new_child 两函数可改。metadata 全等保留。child 要求六字段 JUnit、accepted_command_outcome、child_exit、cleanup、timed_out、wrapper_exit；compact 只可另外含 command、failures、process_pid，逐现有字段与完整结果严格一致。历史 full child 如完整全等也可接受；将来GREEN51回执固定六字段。result完整pin、actual exit、流、child/JUnit/资源检查都不削弱。

new_child 只为已完成 Ruff 的一个 old ROOT-script034b pin增加物理history关系：完整旧29121字节源码先保存archive，核实际SHA；原结果里的path/bytes/SHA不改；恰好一条该记录经archive验证，其余所有记录仍current检查。新GREEN使用新current脚本pin，绝不继承此历史例外。不得改generic check或blanket skip。

修改前完整归档当前ROOT脚本、两角色账本、gate、activation、STATE、PHASE，共七文件。原activation保持不改。当前old gate中的已花费条目保留；后续新gate只增加合法当次审批，不将旧历史pin当当前。输入/完整archive路径/例外精确pin见JSON。

ROOT完整文本与SHA审核两函数delta及新标准库 proof 后，仅可新跑一次120秒 source/provenance metadata proof；不导入/执行settler、不AST、不调用pytest/static或旧runner。独立保存真实stdout/stderr/result。全部script之外产品/测试/Sol脚本保持原样；原prepare/Ruff绝不重跑。

proof成功且ROOT核对后，继续原R192独立GREEN51一次，再原ROOT结算一次，同一独审剩8批，不新seat/reset。当前计划不表示T1/T12通过。任何新错误保留原件立即停。本计划落盘后STOP等待ROOT审核，规划未实施修改或运行proof。
