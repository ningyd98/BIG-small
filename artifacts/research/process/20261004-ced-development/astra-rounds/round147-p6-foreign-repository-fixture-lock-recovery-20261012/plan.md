# R147：foreign repository 夹具锁冲突限定恢复

实际模型 **gpt-6-astra**；规划者 /root/astra_status_plan；2026-10-12。冻结待 ROOT 激活。规划只读文字/hash/JSON/JUnit，没有执行产品、AST 或验证。

原 GREEN20 单次真实 exit1：19 PASS / 1 FAIL / 0 error / 0 skip，原额度已耗1/0。完整 stdout、stderr、invocation、result、JUnit 均保留。唯一失败 tests/test_operational_runtime_closure.py::test_caller_cannot_register_locked_view[foreign_repo] 在测试252行构造另一个真实同DB repository，构造器初始化2297行 schema_migrations INSERT 遇 database is locked；此时 expected OperationalLeaseError 区域尚未进入，不能冒称权限反例已测到。

## 独立定位与最窄范围

原 _tx 已开启真实 BEGIN IMMEDIATE。第二实例有独立 thread-local connection；publication guard 的同线程重入不会使它共享原 SQLite 连接，初始化写锁冲突符合完整 traceback。实际 foreign _operational_transaction 则在初始化/BEGIN前按 session.repository identity 拒绝。构造器 _connect finally 关闭自己的临时连接，不能编造 repository.close API 或改生产连接管理。

仅修改 /home/ningyd/文档/ChatGPT/BIGsmall/tests/test_operational_runtime_closure.py 中 test_caller_cannot_register_locked_view 的 foreign_repo 准备/断言。保留 before=_all_sql(repo) 原位置；紧接其后且原 publication_guard/_tx 前，用 variant==foreign_repo 条件预建一次同DB真实 other，移除原 _tx 内那一处构造。这样原整个SQL基线还覆盖准备动作，不能隐藏应用表变化。

foreign attempt 必须仍在原真实活 _tx 内，仍用原session/job/_tx(other)/propose。允许增加真实 other!=repo、同resolved DB、session.repository is repo、原view连接在拒绝前后in_transaction断言；捕获**原 OperationalLeaseError**并收紧到现有确切 session requires exact concrete repository/job 信息。禁止mockguard/TLS/权限、改数据库/timeout/SQL/lock、跳过/xfail或接受OperationalError/generic异常。

原退出事务后 assert _all_sql(repo)==before 原样保持；仅该variant在断言成功后借原 _evidence 写独立sidecar，记录实际对象/DB身份、真实异常类型/文本、前后活事务观测与wholeSQL断言完成事实。原 _exercise 生命周期、双域/线程、finally关闭、backend/raw/events证据不变；没有新增生命周期或额外探针。完整目标test的其它三分支均已核，无同因初始化问题。

## 输入与历史复用

本计划 JSON 列143个完整绝对输入SHA/bytes。独立127项对照零差异：六源当前/冻结、53protected、原argv、失败case40冻结文件及有限原metadata。原1MB索引所列1048fixture+8symlink元数据保留；不跟随symlink、不SQL打开数据库。ROOT全量2201checks收据/timing-addendum另pin；唯一已知ROOTledger差异是正常失败耗用同步，旧2b9a180f快照不改，current cd1f2822...用于实际1/0，不新立问题。

五生产固定在R145终态；测试原79032B SHA256 9af4327094f3a12d22d7253b37c1ee9ea030cfacf82ab368e70555c927fd5e9e，总40节点不变。其余39节点固定，含同参数test的dict/copy/foreign_thread。R145类型proof与R141既有CPUpositive原件不变、不重跑。

复用19PASS的前提是新的精确source delta证明只有foreign_repo准备/断言变化、其他case路径和五生产不变；原运行永远保留19PASS1FAIL，不能改为20PASS。补验用新的1PASS记录，尚未执行的new19不得提前报通过。

## 最小预算与 ROOT 门

ROOT 先全文读修正diff、实际 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/fixture-delta-proof.py 与 run-budgeted-command.py 并 pin，才可按顺序消耗四个全新各0/1命令：

- test_formatter：`.venv/bin/python -m ruff format tests/test_operational_runtime_closure.py`
- delta_proof：`.venv/bin/python /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/fixture-delta-proof.py`
- test_ruff：`.venv/bin/python -m ruff check tests/test_operational_runtime_closure.py`
- foreign_repo：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_operational_runtime_closure.py::test_caller_cannot_register_locked_view[foreign_repo] --basetemp=/tmp/bigsmall-p6-r147-foreign-repo --junitxml=/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/implementation/foreign_repo/junit.xml`

cwd=/home/ningyd/文档/ChatGPT/BIGsmall；env=PYTHONDONTWRITEBYTECODE=1 / PYTHONPATH=src:.；证据目录为本轮 implementation/命令名。前三命令exit0且ROOT实读source/fixture/proof后方可释放foreign单节点；单节点一次poll/episode，上限1，JUnit必须1PASS0FAIL0error0skip。

delta仅授权一次内存AST/tokenize：验证同一个constructor正确迁移到条件准备；只去除确切新增foreign准备、身份/连接断言、错误捕获/匹配/sidecar并将原构造放回原branch后，整个测试模块AST及原注释/常量必须一致。不得把整函数删除来宣称scope通过。原参数值/IDs、其它三分支、所有helper/import/function完全相同，新增代码只在foreign条件运行；五生产/53protected hash固定。新proof不执行产品导入/compile/eval，不复用旧proof充当新语义证明。

新单节点原raw/JUnit/lifecycle/拒绝sidecar经ROOT接受后，才释放原 new_GREEN19（JSON保留原exact argv/cwd/env/basetemp/JUnit），仍单次0/1，沿原每pytest最多64生命周期约束。原GREEN20已耗不能重跑，positive已耗不能重跑，不新加mypy/整40/旧回归/diagnostic probe。新证据目录与basetemp必须fresh，不删除旧物伪造首次运行。任一新失败保留并停相关修复，再交实际Astra。

只允许本轮计划与input-check/activation/ledger/implementation/validation/step-report/阶段附记metadata；本规划不改STATE/PHASE、Git或产品。所有原失败/冻结/预算源完整保留。

软件A仍需真实补1PASS、原19PASS受限复用、实际new19及独立审查才可评估。验收边界仍 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO；B/C/D未激活，CPU flags不是native/物理/actual/formal证据。

