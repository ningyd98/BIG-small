# R150：生命周期汇总条件与终审读取协议恢复

实际规划者：gpt-6-astra，2026-10-12。冻结待 ROOT 激活。完整输入 pins、两条独立轨道、精确命令和有限额度见 plan.json。

## M1：汇总条件过度概括

R149 单次实际 exit1，spent1/0，2560 checks 中2559通过、1项失败。失败不能改称通过。原计划本身要求每份 lifecycle 恰好一次 shutdown；实施者遵循了这个过窄条件，本轮明确记录 Astra 原计划的条件错误。

独立核对18份原记录：17份 raw_enter1/raw_exit1/shutdown1；唯一 test_private_transaction_helpe2 为 raw_enter1/raw_exit1/shutdown2。全部 session_closed=true，SHA匹配。其冻结测试实际启动第二个 worker，物理 initialize 被明确阻断；软件 factory 的构造器始终返回同一 backend，共享 calls。worker 的 finally 在 initialize 失败时也 shutdown，尚未进入 raw context。因此顺序为第二worker shutdown、外层 raw_exit、外层 shutdown，且两个不同job/lease均终止。这支持“汇总器条件错误”，不支持把当前证据称产品重复清理故障；完整产品正确性仍待终审。

ROOT 新建 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round150-p6-metadata-lifecycle-and-review-recovery-20261012/implementation/read-new19-lifecycle.py，全文及SHA复核后仅一次执行。必须保留原2560项检查及对应关系，只为精确固定的特殊记录规定 shutdown2，其他17仍shutdown1；增加逐场景解释与原调用顺序、两job终态交叉核对。不得 >=1、跳过、去重或改raw。共享日志没有逐实例标签，逐worker归因须标为源代码支持的推断。

新输出 exclusive-create reader/invocation/result/stdout/stderr，真实分离捕获和工具返回；stdout只路径/hash/counts，少于1500字符。原R149 reader不重跑，旧exit1和预算不改。新读取器有1次纯metadata额度，任何不匹配停止，不能同步。

## M2：独立终审读取协议偏离

原001猜测 sources/tests 路径实际exit2；002 bare python实际exit127。此后003 python3与004/005 nl/sed实际执行成功，共3次未经计划的替代读取。19份manifest原件核对一致，完整可得combined保留；没有独立streams，不补造。旧draft是STOPPED preliminary，绝非最终验收，不能追溯抹掉偏离。

激活后原独立 reviewer 可继续，不必等待主汇总完成。只使用 index.sources 的真实flat snapshot绝对路径和 .venv/bin/python stdlib文本/JSON/XML/hash，最多24个有界读取batch，每次源文chunk至多600行。已有阅读可带provenance复用，不为凑数重读。新失败立即停，不再自行替代。最终报告写入本轮review目录，明确完整冻结六源/实际raw、fixture、JUnit、proof桥核查和未决事项，保留两失败三替代读记录。

## 范围、同步与验收

本轮零产品/测试编辑、零pytest/static/AST/import/compile/collect/SQL/probe/Git额度；所有原产品命令已耗用，不重置。独立审查若发现真实产品根因，另列严格新计划，不在本轮试跑或修复。

仅新汇总器所有检查有效且ROOT审阅后，允许一次受控元数据同步：两ROOT账本new_green派生spent1/0/actual0，STATE事实40unique四run/remaining0/终审待完成，PHASE追加。先exclusive保存before件并立即比较字节防并发；不改其他预算、Git、原冻结字节或P6验收值。STATE/PHASE本轮已读取并pin；具体字段边界见JSON。原R149停止时未做同步的事实永久保留。

完成元数据恢复不表示A验收。原40unique是旧19 retained＋修正foreign1＋new19＋CPUpositive1，绝非单次40run。独立终审仍必须完成；StageA上限 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO，B/C/D/native/actual/formal仍不获验收。

