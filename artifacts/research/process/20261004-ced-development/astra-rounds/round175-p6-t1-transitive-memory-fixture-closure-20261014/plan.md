# R175 — T1 传递 Memory 夹具关闭修复计划

实际规划者：gpt-6-astra，/root/astra_status_plan。2026-10-14。状态：冻结，待 ROOT 输入与脚本门控；本轮未实施或运行产品。

## 判定与原始证据

这是已确认的夹具生命周期合同缺口，不是新的 pytest 失败。R174 原 recovery7 的 7PASS、产品和 runner exit0 完整保留。R158 要求每个分配的 event repo 在 finally 清理并记录结果；owned `_b_legacy_sources` 只关闭直接 repo，而 owner/registration/repair-builder 与 bootstrap 的调用链另行分配真实 Memory repo，返回纯数据后不关闭。引用释放不能替代明确的实测 close。

没有测得 OS、线程或数据库泄漏。Memory 只有锁与集合；真实 close 在锁中清理列出的集合，并不清空全部内部字典，也没有 `_closed` 字段。R174 未观察的运行计数仍为 null，不能补写0。

输入完整 SHA、211保护清单、实际七项JUnit和角色账本见 plan.json 与 input-observation.json。17原引用逐项匹配、211保护匹配、父账本均3已用/12HELD。

## 最小实施范围

唯一 gpt-6.1-sol 作者仅修改 tests/test_operational_runtime_closure.py 内 `def _b_legacy_sources(monkeypatch):` 至下一个 `def _b_fields():` 前区域。所有23生产、211保护、纯旧夹具、A80556字节、七测试正文/装饰器、其他helper、R174 JSON规范化、原16tag黄金和父runner不变。

在首个 values 调用前进入局部 monkeypatch.context，仅对真实 Memory 类的 __init__/close 做调用原实现的记录包装。类/权限/锁/返回值保持真实。记录尝试、初始化成功/失败、primary/transitive身份和实际close结果；原primary清理保留，外层finally关闭全部尚未成功关闭的实例，全部尝试且不吞掉错误。最后恢复原方法身份、保存观察并释放引用。

成功仅检查真实 close 返回与其确实清空的 _events/_budgets/_active_contracts/_checkpoints；不得伪造 _closed 或断言全部字典为空。记录实际分母，不能猜分配总数。原返回数据、真实初始化/route/supervision/bootstrapping与断言保持。

本轮runner通过唯一新有限环境变量 BIGSMALL_R175_RESOURCE_DIR 指定每次helper调用的独占JSON资源出口；记录节点、对象/线程身份、分配和关闭分母、错误及方法恢复。无此env的父计划调用仍执行真实finally及本地断言，只不输出sidecar；不得临时改父runner环境或把本轮观察移植到未来调用。

## 历史与预算

两份R174旧账本完整保持：ROOT recovery为 RESERVED_BY_ROOT1/0，author为SPENT1/0；旧ROOT settlement分别HELD_PENDING_ROOT_GATE/HELD0/1。R175独立 disposition 将其有效执行权限置 HELD_SUPERSEDED_BY_R175_NO_EXECUTION；不更改旧字节，不伪造已耗用。

新增仅三个槽：预验证元数据一次120s；精确同七节点恢复一次600s；ROOT元数据结算一次120s。完整argv、有限env、全新目录及资源上限在JSON。原R1583/12、原RED/GREEN、R174两已用动作不重置。静态、A40、Git、网络、GPU/原生新增额度均0。

## 门控与证据

ROOT先复核计划和输入，作者才可修helper并准备两个脚本。ROOT全文审阅修正与脚本SHA后，唯一新metadata动作从已钉住的R174完整候选恢复before-test，归档13旧T1工作报告全部字节，再刷新报告和24源冻结。前后helper之外字节严格相同；211保护/23生产/黄金/父runner全部不变。

ROOT复核实际证明与新runner后，仅运行一次本轮七节点，保存真实分流/返回对象/JUnit/fixture索引/所有资源sidecar。ROOT新结算脚本全文门控后单次核对全部节点、实际资源分母/close/恢复、源与黄金连续性，独立写报告。脚本数量与执行槽明确，不插入额外运行helper。任何新失败停止，不重试。

只有实际7PASS、资源全部可核、ROOT结算合格后，原未用T1独审12批才可启动。本计划不授予T1/B9/fullP6/T12、原生物理、实际或正式验收。R173接口未直接执行的边界保留。旧失败与旧7PASS均不得改写。

