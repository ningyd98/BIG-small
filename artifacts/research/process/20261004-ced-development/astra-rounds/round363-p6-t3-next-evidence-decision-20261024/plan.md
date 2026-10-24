# R363：撤除主动 SIGUSR2 的单因素诊断计划

实际规划者：`gpt-6-astra`，席位 `/root/astra_r363_plan`。本文件与 `plan.json` 是本席位实际生成的计划，不归属于已暂停的旧席位。当前仅计划；不释放运行。

R361 已接受的静态证据显示 R354 子进程 SIGSEGV（−11），约270.106552秒至cleanup；第九次 SIGUSR2 提交先于首次退出观察0.100674956秒。这只是时序相关。R350 原600秒非完成原因仍 UNKNOWN，不能与本次崩溃或 R311 合并。T3仍为2 accepted、第三failed、6 HELD；R354两侧SPENT1/0。

## 唯一下一步

使用冻结的最终 R354 runner/observer/helper 新建 R363 副本，仅撤除整个主动 SIGUSR2 栈采样子系统：注册、发送、READY/control/mask、retire/unregister/close全部撤除，采样机会为0。pytest 自带 fatal-signal 机制、原UTC-memory测试全部断言、最多3个poll生命周期、R357真实资源共存、R358持久化中立、原profile、父OS/HEAD/deadline观察和有限捕获保持不变。优先删除native代码；残留定义必须证明全不可达。

`signal-ownership.jsonl`、`stack-requests.jsonl`、`stacks.raw`、`signal-control.lock`、`signal-state.json`、`stack-ready.json`按计划不存在，必须标记 DISABLED_BY_PLAN，不能计为缺失捕获失败或创建假文件。native恢复/默认状态不可伪填true；`_finish_observer`不能再引用native对象。保留日志/profile/status真实缺失仍是MISSING/UNKNOWN。

## 身份与边界

唯一命令 `R363:utc_no_sigusr2_01`；`plan.json.commands.utc_no_sigusr2_01`逐项给出准确argv、env、cwd、输出。一次全新诊断额度、0行为credit、无retry；不复用R350/R354。子600秒、cleanup15秒（TERM grace5秒）、capture240秒、外层900秒及kill-after20秒。32MiB各raw、16MiB诊断JSONL、1GiB持久树/10000项、4GiB轮次、运行前至少3GiB空间及原采样/HEAD边界不变。

同一实际 Sol `/root/p6_t3_sol`是唯一源码作者/operator。ROOT仅metadata/review/gate/reservation/acceptance，不调用DBengine。产品、测试、fixture、原始证据不改；不优化copy、不放宽超时、不宣称修复。不允许裸import/help/collect/smoke或任何预跑。

## 准备、审查、运行

1. ROOT核验本计划及输入，激活Sol新R363源码准备。仅新未冻结草稿可在限定范围常规Update，随后一次最终freeze。
2. Sol从最终R354三文件形成窄差异，提交完整diff/每处变更映射、AST不变证明与无悬空native引用证明；helper字节不变。ROOT完整审查新差异与受保护profile/资源算法，无需新审计框架。
3. 新`verify_lineage`将R355–R358验收仅作为冻结祖先。旧R358 `persistence[observer]`与冻结R354 observer比较，不能与新observer比较。新protected-profile差异证明及R363 ROOT source acceptance接替当前授权；旧native授权不是新运行授权。
4. 创建新gate、ROOTacceptance、双ledger及各自独立initial快照。可变ledger绝不能进入immutable pins；其运行前状态由CAS验证。还须校验R354双ledger确为SPENT1/0；R350六HELD只历史。
5. ROOT在预约前复核输入/解释器文件链、固定HEAD/分支、无共享writer、排他输出和空间。HEAD必须是`729bce11bbd55a4a869e25e52174da3d0db1825b`。新ROOT reservation先spend；Sol在启动前消费AUTHOR额度。只有随后Sol可执行唯一launcher，任何拒绝/失败不退款、不重试。
6. 独立七阶段捕获、真实group cleanup、终态completion-last保留。Sol据原始证据写简短步骤报告，ROOT独立判定并汇入阶段总结；通过的明确交付路径按用户流程提交、推送并核对SHA。真实运行完成前不移动冻结HEAD。

## 验收解释

撤除验证有效而仍崩溃，可以排除主动 SIGUSR2 是该次崩溃类别的必要条件，不能证明与R354同根因。单次不崩溃不能证明因果、修复或性能改善。测试即使成功仍0行为credit，whole_B/formal_accepted均false；缺失资源数量不填0。计划内非完成/崩溃保留为诊断结果；新的观察器/源码/捕获缺陷或范围扩大须重新交实际Astra，不能现场放宽gate。后续修复或行为重跑需独立计划。

## 冻结引用与文件结构

`plan.json.inputs`含本次实际核对的路径、字节数、SHA256；不重抄539项历史pins。完整继承库存使用冻结R354 `source-gate.json`引用，且所有依赖仍须执行校验。准确新文件清单见`scope`；ROOT与Sol所有新增文件限定本R363目录，运行数据仅`implementation/utc_no_sigusr2_01/`。本计划生成过程未执行候选、pytest、DB或运行探针。
