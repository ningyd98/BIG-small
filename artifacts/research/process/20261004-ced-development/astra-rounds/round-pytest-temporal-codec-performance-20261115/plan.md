# 时间证据 codec 性能：只读诊断与最小安全方案

实际模型：`gpt-6-astra`。状态：**只读诊断完成，未实施、未启动测试/模型/仿真**。遵循最新AGENTS的按需Astra规则；本次仅因严格解码与缓存边界取舍专门评估，不恢复逐错先计划制度。

**建议当前不改代码，先让完整观察器下的四分片完成。** 若在已设cap内正常完成并通过，记录慢项即可，不为速度扩大缓存或削减验证。当前分片运行期间，源码、配置、观察器和既有证据全部保持不变。

## 事实与不确定性

- 完整观察器独立node在120秒外部cap超时，栈采样进程在100秒cap超时；这只是未在cap内完成，不证明逻辑永久不返回。
- 单变量关闭main/threads全局profile的诊断对照已exit0，用时54.44秒（wall约54.72秒）。它明确为 **DIAGNOSTIC_ONLY_NO_ACCEPTANCE**，不能替代验收；并发负载未严格配平，不能声称精确加速比。
- 19个离散Python栈样本覆盖90.16秒：栈顶10次profile、7次_copy、2次_hash；18个栈含from_payload，15个含_history。RSS高水位约100–122.5MiB。采样支持“严格解码与全局观察开销叠加”，不是CPU占比、完整调用计数或无泄漏证明。
- 组合运行在45秒faulthandler诊断输出后出现dumped core，父任务报告exit139。没有native根因证据，不能将SIGSEGV归因于codec，也不能断言timer为唯一原因。
- 当前codec已具有128项/8MiB、单次外层解码作用域的memo；完整canonical文本和cls为键，全部语义与nested校验成功后入表，外层退出清理，copied Context不继承成功结果。不应泛化成跨请求/跨租约缓存。

本轮读到的9个源码/测试/AGENTS文件与分片spec对应SHA一致；仅核对此小范围，未复查全分支。输入绝对路径、字节数、SHA及采样汇总均内嵌plan.json。

## 重复工作的确切边界

_copy重建容器树；_object会再次_copy其子树。累计成本是所访问子树大小之和。LocalEnvelope即使memo命中，也先复制和canonical序列化；to_payload是loads后再复制，semantic/local_time又会拷贝或验证。repository反复读取与derive_local_bootstrap另起完整解码，会重放历史。这些承担隔离和证据验证，不能仅凭“重复”删除。

_history逐事件检查original、operation、CAS、decision、transaction、replay/result hash。**_history_state_hash主动移除history**，因此不能误判它每步都哈希完整增长历史前缀。局部子树重复遍历可能增加深度相关成本，但本次未证明指数增长或memo达到上限。

profile会收到大量Python/C事件，即使随后只匹配少数生命周期code，也有回调筛选成本。关闭profile的对照有诊断意义，但丢失了要求的观察证据。

## 有条件的最小后续

1. 先等现有四分片完成，读取准确来源receipt及完整profile目标时长。沿用现有faulthandler_timeout=0诊断配置与既定3600秒cap；不新增竞争性测试，不变更来源。若完成，首选无代码变更收束。
2. 仅若仍是真实性能阻断，分片结束后在/tmp纯解码诊断中复用既有524867字节冻结promotion seed（SHA `20cbbe651d46f5c62428130db2523a413fcccede2f8851a0e6db2fb56126fb79`）。记录顶层decode次数、完整键hit/miss、copy节点/累计规模、semantic成功次数、memo溢出、wall/CPU/RSS；真实委托原函数，异常照常传播，不调用worker/模型/仿真。计数运行也不是验收。
3. 若局部测量支持，唯一首选实现候选是 `_copy` 的常量因子优化：None先返回，type(value)只算一次，去除exact bool/str分支里已由外层证明的冗余isinstance。原int范围、finite、Mapping优先次序与items副作用、重复key、子类拒绝、异常和深隔离必须保留。此变化不减少递归访问数；实际收益可能很小，不能先承诺速度。
4. 现有 `test_local_temporal_copy_dispatch.py` 已覆盖类型/别名/Mapping虚拟注册及items异常矩阵，优先复用。再验证memo上下文/上限、recursive projection、promotion源与期限/历史负例，以及完整profile原目标node。若来源有改动，必须生成新验证receipt，旧分片结果不证明新来源。

`_history`不变definition hash也有重复，但收益未量化，不与_copy同时改。更大缓存、删复制、跳历史校验、动态模型缓存均不属于本轮最小方案。

## 安全与验收

禁止跨顶层/线程/Context/租约持久缓存；禁止对象id/弱键复用；禁止把detached描述当实时权限。不得改租约、原始期限、源绑定、历史重放语义、成功标准或live registry行为。不得停用profile、减少生命周期观察、跳过wait_observer或放宽断言使验收通过。

未来如实施，范围仅local_temporal.py::_copy及必要的现有copy测试，不改worker_runtime、visual_bootstrap或operational观察器。必须等当前验证结束，复核SHA，使用Python3.12共享venv、固定隔离树PYTHONPATH、禁止字节码/pytest缓存、唯一/tmp输出。保留canonical字节、digest、projection、负例拒绝和可变输出隔离；完整profile证据仍是验收必要条件。

若全观察器运行可完成，无须为了优化而优化。SIGSEGV若再现，另取native最小证据，不能用本计划给它未经证明的codec归因。本计划不宣称当前完整测试已经通过。
