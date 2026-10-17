# Astra Round90：文档收尾既存收据限定恢复

规划 gpt-6-astra；ROOT执行。PLAN_ONLY，全部R90文件local-only；不增发布路径，不重跑原脚本。用户已授权Git整理推送，本轮只恢复6路径文档收尾。

## 原失败和当前停点

ROOT报告tool2a5870 exit1，/tmp/bigsmall-final-docs.py第57行 `assert not (w/p).exists()` 触发AssertionError。原脚本先写了两树的3docs，之后首个RW1收据已经存在而退出；没有stage/commit/push、SDD追加或prepared-documents.json。本代理读取完整保存脚本，failure-evidence.json保留ROOT提供的执行出处/错误位置和独立读取的真实源码行；原完整stdout未提供，不编造工具输出，也不重跑失败。

独立只读确认：6路径manifest中的RW1/root-delivery.json已tracked，2957 bytes且与primary原件一致；OC2/P2两收据在候选不存在。report3317B为untracked且两树相同；status候选30142B、phase候选1756B均tracked，与primary的不同历史正文是预期，不合并覆盖。当前各文件的分立SHA/bytes、manifest、原脚本、SDD和观察pins见plan.json；恢复前全部复核。

## 唯一允许恢复

1. 保留原脚本/失败收据，写新的有限恢复操作，不从头执行/tmp/bigsmall-final-docs.py，不重复生成报告、重写status或追加整个P1/P2章节。仅按metadata-paths.json的3收据遍历：存在时必须逐字节等于primary且符合manifest原pin，再确认Git tracking；相同原件直接复用，不能算新增变更；若不同立即STOP并留证，不覆盖。不在候选的仅新建复制OC2/P2两项，复制后bytes/SHA一致。已有但untracked的非预期状态也显式记录/停止，不假定曾提交。
2. ROOT已要求极小文案修正：两树report中恰一次将“本汇总及三份既有收据另作有限文档提交”替换为“RW1收据复用既有提交；本汇总、OC2/P2两份收据与最新状态另作有限文档提交”。只替此字符串，保留后文及所有其他字节。再于两树report和两树phase-summary末段各追加且仅追加一次：

   `R90 收尾恢复：准备器误把既有 RW1 收据视为应新增文件，现复用字节相同的原件，仅复制 OC2/P2 两份收据；六个选定路径对应五个实际变更，原有 P1/P2 章节保持且未重复追加。`

   写前断言旧句恰一次、R90新句未出现；若已完整存在按已完成处理，不重复追加；其他混合状态停止核对。status完全不改。两树report最终相同，phase各自原历史保留，仅同一句追加；不得为了两树hash相同覆盖其不同历史。
3. SDD仅本地补一次原脚本第59行with块中的原定append文字。先核当前ledger pin与目标marker计数0；使用原块中已保存的确切字符串，写后确认旧字节是新文件完整前缀且marker计数1。若已有相同完整追加则复用，不再append；若仅部分/不同内容则停止，不重写ledger。SDD不发布。
4. 补建local-only delivery-final/prepared-documents.json，记录selected_paths=6、each source/worktree最终pins、RW1 reuse=1、receipts copied=2、真正changed_paths和count。不能把selected6误记为new/changed6；当前预期changed5：report、status、phase、OC2 receipt、P2 receipt。用真实相对父851b80c88c242007a740dae778671bdf98ab330c的diff/index状态确认，不靠硬编码删去第六项。若变化集不同则停止分析；原metadata-paths.json选择集合与原before pins不回写。
5. ROOT人工审阅最终3docs的有限diff、两新增原收据和RW1复用证据，确认R90文案与真实状态一致。仅stage manifest中实际changed5，不stageSDD/R90/local receipts或其他路径；校验staged集合及逐blob pins。对此文档提交运行正常完整严格 `git diff --cached --check`，要求真实exit0并保留输出/退出码；不能复用代码提交的exit2例外或改原件取绿。意外失败另交Astra，不扩大修复。
6. 确认文档父级仍为已推送P2的851b80c88c242007a740dae778671bdf98ab330c，ROOT在同交付branch、同origin明确non-force提交推送并核对本地/upstream/live远端完整三SHA一致。最终root-delivery.json仅本地保存实际文档commit/父级/三SHA/selected6与changed5，避免自引用amend。原RW1/OC2/P2收据仍记录各自历史推送，不改其commit字段。

## 验收边界

不改产品、测试或原实验字节，actual/test=0；用户1007及嵌套脏树保留。原三文档章节不重复，既有同字节RW1收据复用、缺失两收据原字节复制，SDD只补一次，6选择与5变更分别记录，严格文档检查及最终三SHA真实核验。R90计划/观察/恢复证据、prepared-documents与SDD均local-only；发布范围始终原6路径集合，实际变更5。GRASP/full future D与formal限制保持，不把文档交付当新研究验收。
