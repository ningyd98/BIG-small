# P5 完整不同作者审查：R110

**NEEDS_TEST_COVERAGE_FIX；不接受完整 P5 PASS。** 实际 gpt-6-astra，不是产品实施作者。完整本轮源/用例/证据审查发现 **1 项阻断性测试覆盖缺口，未发现其他有依据的新产品缺陷**。R110 的两修复节点确实通过，但这不能补足原测试对文件漂移的独立验证。

## 唯一待修项 C1

`tests/test_operational_windows.py::test_source_and_budget_changes_invalidate_window`（冻结 R110:426 起）先改真实 SQLite job.timeout_seconds，使 operational_windows._check_live 检出 job source 不符并调用 _revoke_worker。恢复 SQL 值后 owner._closed 仍为 True；接着修改 device.py 再 check，会在 _check_live 最前面直接 UNKNOWN，根本未执行末尾 pin_worker_source_inventory。因而文件漂移断言不是独立动态证据。master Task5 Step5/R100 source变化失效要求尚未由该测试验证。源码本身存在真实 SHA 重读，本审查不把该覆盖缺口宣称产品漏洞或运行失败。必须在新鲜 owner 上独立建立 VALID→单文件突变→拒绝，保留真实 worker/SQLite/source路径，不能仅靠读到产品检查而宣布完成。

## 真实结果与范围

独立匹配最终十份 P5 源/测试 + 三份 fixture 的当前字节、冻结 SHA、逐份 snapshot（13 项全部一致）。已核 R110 原 command-result 和 stdout/stderr hash，formatter/delta/Ruff/formatcheck/GREEN各 exit0；新 JUnit 精确2unique=2PASS。独立解析 R107 原30PASS+2FAIL和R110两原node，结合限定whole-file逆向AST证明源码与实际diff，旧30结果适用；组合为 P5 32 unique 覆盖，不是新跑32。原 R105批次 JUnit中60个OC1 PASS另行适用复用，源/测试/config保持；不称新跑92，不抹掉原批次32失败。

R10027RED、R10592（32FAIL/60PASS）、R10632（6FAIL/26PASS）、R10732（2FAIL/30PASS）原件均保留并独立解析。R107与R110作者proof是原已执行证据；审查全文读了脚本、断言及原输出，并读精确实际diff，不重新运行proof或产品测试。没有以作者report的PASS字段替代源码/原件检查。

## 需求到代码和用例

- **startup/original origin**：`worker.py:213–233; operational_windows.py:166–225,327–354`；用例 `startup_origin_precedes_reset_and_settle; public_worker/source`。real poll_once/_execute RUNNING+unique attempt before D bracket; bracket encloses original time tuple, handoff prepared before backend initialize; late runtime cannot refill。
- **private handoff/lifetime**：`operational_windows.py:265–280,538–612; worker_runtime.py:262–336`；用例 `public_worker; ended_prefix; foreign_thread; fourcleanup`。exact type before dict lookup; one-shot pending/handoff, identity registry and owner-thread scope, finally pop/close; no Python hostile-process sandbox claim。
- **AGE/HARD/parents**：`operational_windows.py:386–534; OC1 within_age/before_deadline`；用例 `five_seconds; deadline[3]; parent_age; nonzero_bracket; overlap; foreign_pair`。own and inherited AGE use paired current<=cap, HARD current<deadline; hard-only descriptor min, effective tie exclusive, source/time untouched。
- **capture/plan/bootstrap**：`worker_runtime.py:336–371,984–1094; visual_bootstrap.py:766–792`；用例 `categories bootstrap/capture/plan; cache; late reply`。real reserve/complete enclosing-effect brackets; acquisition registered once; reply inherits originalcapture; true existing UTC/CAS remain。
- **grounding**：`worker_runtime.py:1252–1272`；用例 `category grounding`。original requirement ordinaryTTL and exact observationid/checksum gate actual publish; shared reference expiry tested separately。
- **supervision**：`worker_runtime.py:748–822,878–944; supervision.py:52–75`；用例 `category supervision`。real capture/plan/commit, currentD plus frozen requirement/maxage; max5 CONTINUE/max6 DISCARD; three-module CPU UTC context local and restored, no actualUTC claim。
- **marker**：`marker_association.py:288–340,452–470,632–639`；用例 `R110 marker node`。real OpenCV/source/asset checks, immutable descriptor, positive+sourcechange+actualexpired negative; DEVELOPMENT_ONLY/NOT_ADMITTED retained。
- **condition/VisualEvidence**：`conditions.py:131–150,313–322; models.py:30–38; worker_runtime.py:1170–1193`；用例 `condition category; utcjump; typedexport`。positive stoppedTrue semantic corrected; local D explicitref with strict policy, legacy withoutref retains UTC; nested frozen evidence supported。
- **newcommit/history/legacy**：`operational_windows.py:703–742; bootstrap:766–792; supervision:824–863; actual event Memory/SQLite calls`；用例 `R110 replay; category bootstrap/supervision`。history checked before private scope consume; new transition exactdigest/owner/ids and no downgrade; public descriptor alone not capability; legacy byte equality against independent preP5 source。
- **strict descriptors/scope**：`operational_windows.py:746–1070`；用例 `typedexport; externalUTC; utclease`。no coercion/cycles/nonfinite; typed AGE/HARD/bool rejection; native unavailable/futureunknown/restartsuspendunmeasured cannot upgrade; UTC_LEGACY_VETO clear。
- **source/budget livecheck**：`operational_windows.py:286–324; worker_owner.py:253–290`；用例 `source_and_budget_changes_invalidate_window`。product source hashing exists, BUT old test source half is masked by already closed owner; sole blocking review finding。
- **cleanup terminal evidence**：`worker.py:233,295–345; operational_windows.py:_revoke_worker`；用例 `cleanup[4] + original CPU DB readonly`。exception/cancel patched function actually called after_run; DB exception BLOCKED_BY_ENV CPU failure, cancellation CANCELLED CPU cancelled; normal callback still simulated episodeFAILED, not physicalsuccess。

## 必须保留的证据界限

七类别共有过期/rebound尾部是 `_check_reference` 原窗口负例；真实 condition/marker另有消费者过期负例。不能写成七类都分别执行了生产消费者过期路径；原计划不要求额外七套独立生产负控，本审查不扩张此分母。

R107 工厂实际SQLite job/event新提交已被CPU路径执行；Memory的新增codec/transition路由经源码核对调用同一typed derive，R110 legacy对照另实际使用Memory。完整Memory/SQLite D事务/lease/dispatch正链是P6，未假称本轮全部闭合。源/lease检查与OC1读取之间仍非原子事务；真实D租约未生产，descriptor明确UTC_LEGACY_VETO。租约心跳在别线程保持旧路线，不减不同域数字。

cleanup异常/取消不是只patch名字：factory during_episode返回后实际_execute调用被patch函数，except分流并finally撤销；原CPU DB四条终态附在JSON。正常cleanup参数只表示回调正常返回，factory episode本来返回SOFTWARE_FACTORY_ONLY/FAILED，不能冒称真实任务成功。异常的实际仓储终态为BLOCKED_BY_ENV（CPU failure），取消为CANCELLED。

三fixture逐项SHA与冻结spec完全匹配，gzip独立解出2113847B，SHA c4067a0cdf272f93afc69d7d33d805ed6290808e3b0ccdc735c8ad60213b12df，和旧原frame逐字节相同；两个JSON与spec序列化一致，六源/asset hash当前全部匹配。只证明旧诊断图像的CPU复用，绝不新actual/source资格。旧yaml未刷新。Git有限交付必须保留三fixture与两个R102/source-before legacy codec原件；不需要完整raw/DB。

R110字段comprehension使用标准fields/init并排除新字段，旧class对照payload/digest/recordJSON与后续supervision/immutable/replay全部真实执行通过。R107 normalized canonical只比较未变的plain副本，旧JSON不放宽extra/type；public from_worker先精确类型再registry查找。三项OC1能力限制保持不可升级。

本审查的inputs/13pin核验/全批次原JUnit节点/命令原件/夹具检查/有限DB查询在JSON。审查本身product/import/test/static/actual/Git均0。下一轮只修C1测试覆盖，复核原31适用性后完成最终补充审查，再由ROOT决定有限Git/P6。P6、native完整动作、actual和正式研究均未通过此审查获准。
