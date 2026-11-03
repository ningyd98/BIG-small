# R399 — ETEAC 重试初始化同锁递归修复

实际模型 gpt-6-astra；先计划后实施。HEAD `ac6351b66a6dd05fb67aadd59935ce5726748709`，研发分支 `research/20261004-continuation`。目录日期为 UTC 2026-11-02；执行时间如实记录。SHA 与调用边清单见 input-audit.json，精确命令/预算见 plan.json。

## 根因与限定方案

R396 已批准动态证据确认：ETEAC 在 SQLite initializer 持有普通 Lock 时调用公共 get_retry_budget，装饰器再次取得同锁；四组栈和对象身份一致，runner 不返回、close 未进入。不是关闭阶段或性能猜测。

只改 sqlite.py：把 get_retry_budget / get_verification_budget / get_recovery / get_event / get_state / get_replan_apply_record 的原 SQL/解码/校验体提为私有 unlocked reader，公共方法保留装饰器与原语义。仅已确认持锁的内部调用改用这些 helper；包括 _consume_retry_locked、恢复内部 list 链、_replan_cancelled_locked、_visual_group_locked。内部 list_recoveries 另用私有 helper，外部列表的路由保持。非装饰 active-contract/checkpoint/list-events 调用不盲改。

保留普通 Lock、BEGIN IMMEDIATE、真实 writer guard、事务/commit/CAS/rollback、拷贝/hash 校验和私有 scope。禁止 RLock、去锁、释放锁后读、__wrapped__ 绕过或修改 protocol。memory 未发现同类持锁公共调用，不修改。这样覆盖同根因后续位置，不仅解除最初初始化。

## 测试先行与真实结束证据

新 tests/test_eteac_retry_lock_regression.py 使用短受控子进程运行真实 repo，<=10秒自动失败并 reap，不让 pytest 永久挂起。唯一 RED 节点先对原产品运行，保存已知 sqlite→protocol 栈；setup/import错误不是 RED。然后最小修复、同测试 GREEN；既有 replan activation / recovery lifecycle / verified lifecycle、三个 visual repository 模块、四个明确 operational fence nodes、四个短 worker/repo nodes 各一次，原断言不改。全部精确 argv 已列 JSON。

最后新 DB、真实单个 MOCK worker：先排 ETEAC 再排 PCSC sentinel；原 S01/seed0/NORMAL/LEGACY/cache/retry/supervision/30秒输入不变。ETEAC 自然成功后 sentinel 仍 QUEUED attempt0，再第二次 poll 消费并成功，每次≤30秒。断言真实成功结果、attempt结束、lease释放、线程/fd关闭；不手改终态，不启 HTTP，不重跑旧诊断或浏览器。在批准 native child 内调用官方 current_source_tree_hash() 登记修后工作树哈希，并记录 patched 源 pinset；不能把工作树修改冒充干净 HEAD。

## 前置、预算与交付

既有研发 checkout/venv、workspace-write/restricted/.git readonly；无 socket需求。沿用 R376小 supervisor/R373记录器，operational stage 才启原 R235前置及 R381冻结goldens。不复制复杂诊断driver、不另增通用helper审批链。

新独立 wall1800秒，从 RED前开始，包含实现/七阶段/终审/交付；阶段 cap 60/120/300/180/180/90/90秒，各cleanup≤15秒，0retry、串行。禁止全4732 suite、长T3复跑及原预算重用。新根因/范围外失败即下一 Astra轮。

最终独立代码及证据审查后，只明确路径交付 sqlite.py、新测试和本轮精选小记录。DB/WAL/SHM/raw/cache/旧原件/两dirtygitlink不纳入；保护 main、其它refs及嵌套状态。普通commit一次≤60秒、push一次≤60秒、exact remote核验一次≤60秒，确认本地/上游/实时remote三SHA一致。后置回执local-only。原 browser 19问题、物理/正式研究不因本轮软件成功升级。

本规划只读静态核对，尚未修改产品或运行测试/SQL/网络。
