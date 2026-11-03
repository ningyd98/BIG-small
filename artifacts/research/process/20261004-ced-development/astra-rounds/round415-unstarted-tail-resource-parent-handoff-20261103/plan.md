# R415 未启动尾部资源目录前置与条件式续跑

实际规划：**gpt-6-astra**。承接用户一次全量长测及报告授权；只修改新runner派生版本的目录准备，不改产品/测试/原冻结脚本，不重跑已STARTED节点。精确SHA和实施细则见同目录plan.json。

**已证实的静态问题：** 原execute先排他新建tail根，再逐项`.mkdir()`；resource_dirs包含`r223/resources`，但未先建`r223`，因此真正走入该路径会在run_one之前抛FileNotFoundError。当前075仍在运行，不能把这个静态事实写成已发生运行失败，也不能把075耗时归因于它。076规划时只有预建资源目录。

- [ ] 复核pins及076未启动，记录R414 parent实际PID/starttime/session。先写R415 block-intent，再在原076/result.json排他写`BLOCKED_PRECONDITION_R415_RESOURCE_PARENT`、`launched=false`、`pytest_attempts=0`、`returncode=null`；不造invocation/child退出。写后复核无竞争。
- [ ] 当前075继续，无信号。等待R414自然终结：可能在075尾部目录错误退出，也可能完成075后在076管理guard拒绝处退出。分别保留真实异常/退出码，不预填原因；没有触发目录错误则记NOT_TRIGGERED。必须取得实际session terminal、确认原parent身份消失、owned cleanup/source成立。
- [ ] 从完整R413/R414账本（含073后继和已有tail）汇总STARTED，保留所有已开始的不完整结果。075只有可信完整事件证明从未STARTED的节点才按原序派生新tail，单node原600秒一次；旧partial目录原样保留不用。076确证零行为才新id/fresh目录完整原4节点、原1800秒；其他从未invoked阶段沿原顺序。
- [ ] 新R415 resumer复用原run_one/bounded_stage。派生execute只改资源子目录为`mkdir(parents=True, exist_ok=True)`，新tail根继续排他创建；另允许新tail id加R415 namespace避免碰撞。所有预算、环境、依赖、过滤、清理和source逻辑不变。AST归一化精确检查仅上述差分，compile静态检查即可，不跑坏前置或smoke、不新建helper审核链。
- [ ] 075已终态不可再次execute(075)；其pending tail直接按原规格调用run_one。未来模块用新派生execute，保持只续从未STARTED节点。不要把R414仅扫原stages/queue首项073的硬编码复制进新恢复器。
- [ ] 汇总真实结果、退出/清理与唯一4753 ledger。075已开始INCOMPLETE不重跑；新tail通过不冒充整个原模块完整PASS。076 guard是零行为管理状态，不能双计4节点。073已7P保留，其环境修正不得扩散到其它SIMDB。

不改R413/R414计划、spec或运行内存，不删除partial目录，不给已用额度退款，不发信号。parent未终结、guard竞争、事件不确定、源漂移或清理不成立则停相关恢复，不猜未开始。测试失败继续按原全测报告规则；最终统一fresh review与精选交付，无新增Git额度。

本计划仅静态制定，尚未实施guard/续跑。自审已覆盖自然交接两分支、原始退出来源、目录修正范围、successor总账与无重复行为。
