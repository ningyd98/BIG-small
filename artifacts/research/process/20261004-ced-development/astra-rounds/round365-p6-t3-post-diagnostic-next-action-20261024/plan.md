# R365：如实关闭R363证据，实施严格复制的定点效率修复

实际规划者 `gpt-6-astra /root/astra_r363_plan`。当前无运行release，旧HEAD `729bce11bbd55a4a869e25e52174da3d0db1825b`。

R363原result显示600秒child_wall触发，child−15，cleanup已reap且进程组为空；无再次SIGSEGV。资源/JUnit/case与最终observer状态不完整，数量UNKNOWN，行为credit0。不崩溃不能证明信号因果或修复。最后完整profile checkpoint的_copy329744次、_object2555次，LocalEnvelope52call/51return，随后30秒观察器CPU饱和；这只支持已观察前缀的重复工作，600秒根因仍UNKNOWN。

## 先关闭两处报告问题

保留Sol错抄与更正消息，单独标为operator-reported转录；从原raw-process-ledger实际schema及冻结命令核对env，不能从不存在的store恢复或伪造a20e01原始bytes。ROOT从原JSON文件重读选定字段，每次显示最多8000字符，派生记录最多64KiB，必要时明确分页并给hash/count；不能去掉截断warning后把残缺JSON当完整。原截断结果与parse失败保持不变。

ROOT独立核对原result/completion/七receipt、源与捕获副本、deadline/exit/cleanup及缺失；另写disposition。先冻结R363 ROOT ledger before快照，再按原reservation CAS RESERVED1/0→SPENT1/0，保留其余元数据，不退款；AUTHOR已SPENT不改。Sol写简短步骤报告，ROOT汇总。接受有界观察完整性与行为证据不完整须分别表述；不改原result/completion。

## 选择定点源码候选，不增加诊断

只改 `local_temporal.py::_copy` 一个条件：`type(value) is dict or isinstance(value, Mapping)`，原公共严格key校验和递归复制loop保持原样。这消除精确内置dict上冗余ABC判定，依据是确定的源码路径及已有调用量，不要求再测一次。

**列表分支保留在Mapping后面，不提前。** 提前会改变虚拟Mapping注册或替代Mapping情况下的优先级。dict子类和其他Mapping仍完整走原判定、items调用、重复key校验和异常传播；list及scalar子类规则保持。整数边界、float有限性、bool区别、str严格key、对象脱离、重复别名各自复制均保留。不碰_object、schema/history/semantic、accessor、memo128项/8MiB、Context所有权、canonical/hash或worker/clock/lease。

这是减少确定冗余成本的候选，不宣称已找到600秒根因或保证可在600秒完成。

## 有限验证

四个新HELD槽位，准确argv/env/output见JSON：

1. `copy_red_01`：在原产品源码运行新严格复制契约测试，仅允许最终“exact dict不应重复ABC判定”断言RED。语义断言先运行。
2. `copy_green_01`：同一测试、同一断言，仅上述一行产品变更后GREEN。有限正反值、别名与双向修改脱离、定制Mapping/子类/items异常及严格数字/key验证；委托观察只统计真实ABC调用，不替换校验结果。
3. `codec_regression_01`：原decode_memo、projection_closure、promotion_bindings三文件原样；所有真实seed与依赖先静态冻结。
4. `utc_memory_01`：原完整UTC-memory节点，全部断言、两个时钟偏移场景及late-return保持，最多3poll，真实原资源侧车。无新profile或SIGUSR2。

每槽child600秒、cleanup15秒、capture240秒、outer900秒/kill20秒；并发1，不退款/重试。ROOT完整审查新runner的有限继承差异、测试与产品差异后，新双ledger、各初始快照、RED/GREEN独立gate与acceptance和逐次reservation才可运行。无预跑import/help/collect/smoke/DB。纯codec槽位需静态证明0poll，资源stage标NOT_APPLICABLE，不伪填sidecar；UTC不能豁免资源缺失。

保持当前HEAD不变完成此系列；RED gate绑定原源码+新测试，预期RED后才改产品，GREEN gate绑定精确工作树改动。旧R363 gate不能授权新源码。交付验证后按明确路径commit/push并核对三方SHA；之后新运行需对精确新HEAD重建适用gate，禁止任意descendant放行。

## 验收边界和T3后续

微测试仅证明语义与减少冗余判定；原UTC节点在600秒内完整断言、真实资源和捕获通过并经ROOT独立接受，才形成该变更源码上的节点候选。R363不计T3。变更后旧两个accepted仍是历史，完整T3须在后续准确冻结和新逐节点额度下评估/复验全部九节点，六旧HELD不转移；再依原路线进入B9/fullB→C→P7/P8→D。R365未释放后续节点。

除指定RED外的新失败或再次非完成均留存并交实际Astra下一轮，不延长时间、不削弱断言、不默认追加诊断框架。26原输入pins、补充runner/helper/readout pins、原始问题、各文件范围和完整前置见plan.json。规划阶段仅原文件/源码静态读取，未运行候选或DB。
