# 补充：区分 post-cloud 与动作后帧

规划模型 **gpt-6-astra**；状态 **PLAN_ONLY_NOT_IMPLEMENTED**。只读诊断及计划证据写入，没有改测试/生产，没有运行测试、仿真、网络或模型。父目录原plan.md、plan.json及SHA256SUMS字节保持不变，本子目录独立校验。

原日志`offline-strict-fault-green-02.log`记录 **3 failed in 13.51s**、退出码1，原样冻结于evidence。独立核对三case：marker_frames均为`before, post-cloud, pre-00-move_above, after`；两阶段规划通过，point4/cloud1，网络尝试空，PRE/POST/HARD均为正确终止原因、执行数0/1/0。`post-cloud`是规划后的合法观测，旧`label.startswith("post-")`把它误认为动作后观测，是三个失败的共同根因。不存在真实post-00/后续pre/terminal帧。

仅修改`_assert_reached_safety_boundary`中的标签条件：保留`pre-00-move_above`必须存在，改用`set(labels) <= {"before", "post-cloud", "pre-00-move_above", "after"}`。明确允许集合比泛前缀语义准确，也拒绝未知标签。不要改生产帧名称，不跳过帧检查，不放宽真实post动作/后续pre/terminal约束。

完整保留真实规则原verdict必须allowed、规则结果非空、POST委托深度恢复、delegated_pre对象身份、contract/step对象相同、注入恰一次、精确原因与执行数、无settle及end_step==controller_return_step等全部断言。插桩本身不再修改。

验证先保留本次RED；实施后对4个合法标签和post-00/post-01/post-07/post-99、pre-01/pre-07、terminal及未知post标签作无仿真的分类核对，前4允许、其余全拒绝。计划诊断的纯集合表见label-oracle-table.json。随后父任务按原计划同环境、同权限审核规则，用全新`/tmp/bigsmall-offline-strict-fault-green-03`（存在则更换新编号）精确复验PRE、POST、HARD三个节点，预期3 passed无skip；保留日志及完整新episode。再核对原3个规划失败负对照、测试文件Ruff及禁止变更源码SHA。新失败停止相关修复并再交Astra。

输入绝对路径/大小/SHA与快照见inputs.json；helper切片SHA见plan.json，三case完整原输出字节清单见episode-file-hashes.json。并行完整性/phase变更按另一计划继续；实施前对本helper复核，不覆盖其他函数，不把已授权修改误称未知漂移。原始计划和失败证据不可覆盖。

本补充只修测试标签分类，不宣称三个节点已经通过，不替代27例离线闭环、真实模型/硬件或研究验收。
