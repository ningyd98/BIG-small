# R420 Phase11 返回时 SQLite 连接生命周期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 延续 R419 的 `superpowers:executing-plans`；用户已授权开始修复，本轮是新问题的 Astra 补充计划，不另起执行方式确认。

**Goal:** 在 adapter 返回或抛出异常前显式关闭自己持有的 SQLite 连接，并用独立测试区分产品句柄和观测器影响。

**Architecture:** 只修 `_sqlite_summary` 的连接拥有范围，保留事务退出及SQL顺序；返回前关闭与计算最终DB hash有明确先后关系。独立FD测试不被R419外层status断言遮挡；正常/异常路径用窄范围真实连接跟踪，原生路径另作无替身验证。

**Tech Stack:** Python 3.12 `sqlite3`、`contextlib.closing`、pytest、Linux `/proc/self/fd`。

**Spec:** 根AGENTS、已采用的R418/R419计划、本轮 `intake/observation.json`。实际规划模型：`gpt-6-astra`。

**状态：PLANNED_NOT_IMPLEMENTED。Astra本轮未运行任何测试、产品或SQL，未改产品/测试/Git。**

## Global Constraints

- 只允许修改现有 adapter 与 R419 新测试文件；不改 repository/worker/guard、默认模式、TTL/timeout、旧raw/JUnit/audit。
- R419的17个纯投影和4个原生status RED仍属原计划预期失败；R420只处理新增返回时FD发现。
- 不用GC、删DB/WAL/SHM、隐藏FD、放宽授权或进程退出作为显式关闭的替代。
- 成功交付仍按明确路径normal push并核对三处SHA；Astra规划者只写两计划文件。
- R419真实性与R420资源修复合并一次最终fresh Astra review，不加helper审查链。

## Review Focus

- 原FD断言没执行：新增独立FD测试先断资源，不依赖外层status。
- 观测器自己打开连接：在它打开前及显式关闭后分别采样，并独立验证观测器。
- 异常路径遗漏关闭：真实连接注入COUNT/VACUUM/checkpoint错误，原异常保留且close执行。
- GC偶然关闭：窄范围跟踪保留测试强引用，证明显式close；原生无跟踪对照仍须无FD。
- 先hash后close：hash必须在拥有的连接关闭后计算，并与关闭后的实际文件一致。

---

## 原始证据与根因边界

R419 `validation/red-native/native-blocked-audit.json`在adapter返回、观测器查询连接显式close后记录 **4个本run SQLite FD**：主DB两项、WAL一项、SHM一项；未释放lease=0、heartbeat=[]。外层status断言先FAIL，后面的FD断言没有执行。因此这是审计发现，不能写成“独立FD测试已经失败”。

原17个pure+4个native均为预期call断言FAIL，setup/teardown通过；两stage正常exit1、reaped=true、remaining_live=[]、source_drift=[]。四FD属于API返回时进程内状态，不是测试子进程结束后的宿主残留，不能宣称supervisor清理失败。

**事实（高置信）：** adapter `_sqlite_summary` 使用 `with sqlite3.connect(...) as conn`，没有显式close。该上下文处理事务退出；它不保证关闭连接。随后 `_path_hash` 在无明确close的情况下计算。repository `_connect` 对自有连接有finally close；活动事务连接是借用，不应在此擅自关闭。测试 `_native_audit` 同样有finally close。

**高置信生命周期缺口、尚未完成FD逐项归因：** summary连接可能解释部分或全部句柄，但原audit没有连接到FD映射；四路径不等于四连接。观测器访问同DB是否影响SQLite底层句柄记录也未被原证据排除。先建立before-observer/after-close及限定连接跟踪，不先宣布四个FD全部来自summary。

## 限定文件与接口

- Modify: `src/cloud_edge_robot_arm/final_evaluation/adapters/simulation_runtime.py`，本补充只改 `_sqlite_summary` 生命周期及必要的 `closing` 导入；R419已有真实性范围仍独立有效。
- Modify: `tests/test_phase11_adapter_receipt_truthfulness.py`，新增下列测试、FD采样及观测器辅助函数。
- 不改：`sqlite_repository.py`、`worker.py`、R413 bounded supervisor、R419 run_stage、旧失败断言及模式/研究门禁。

保留 `_sqlite_summary(database_path: Path, *, output_root: Path) -> dict[str, Any]` 的签名、表集合、checkpoint/VACUUM顺序和返回schema。实现选择明确为外层 `with closing(sqlite3.connect(database_path)) as conn:`，内层 `with conn:` 保留原事务提交/回滚语义；返回dict及 `_path_hash` 必须在两个上下文都退出后执行。不要只删除原事务上下文，也不要移动hash到close前。

测试辅助接口：`_run_sqlite_fds(output_root: Path) -> list[dict[str, object]]` 读取本进程FD号/target，必要时device/inode；匹配新run根的实际路径边界，保留DB/WAL/SHM，不做全进程FD总数断言或宽泛字符串过滤。`_unreleased_lease_count(database: Path) -> int` 从现有audit抽出查询，继续显式finally close。`_native_audit`新增 `before_observer`、`after_observer_close` 两份FD记录，原 `run_sqlite_fds` 保持after-close兼容含义。

### Task 1：先取得独立资源RED并排除观测器影响

- [ ] 新增 `test_native_adapter_closes_run_sqlite_before_observer`：默认draft、真实Worker/SQLite/recovery运行一次；返回后先采FD，再执行显式close的lease观测器，再采FD。先保存两份采样、lease/thread和原receipt路径，再独立断言两份FD都空；不先断status、不替换运行结果。
- [ ] 新增 `test_sqlite_summary_closes_owned_connection[success|count_error|vacuum_error|checkpoint_error]`：真实新scratch DB/schema，用 `sqlite3.Connection` 子类记录close，强引用保留到断言后。分别正常返回或在首个COUNT、VACUUM、最后checkpoint注入一次sentinel异常；断言close恰一次，异常原样传出，不制造成功summary。成功时hash观察器先断言已close再调用原hash。
- [ ] 跟踪只绑定adapter模块的 `sqlite3` 变量到测试局部proxy/namespace，其connect调用原sqlite3.connect并传factory子类；不monkeypatch全局sqlite3.connect，避免影响repository和观测器。测试追踪不是生产清理方案，不调用gc.collect或删除引用迫使析构。
- [ ] 新增 `test_native_audit_observer_closes_own_connection[success|query_error]`：在独立新DB建立最小lease表后关闭setup连接，验证观测器正常查询/故障查询均finally close，前后本DB FD为空。它不运行adapter，也不能清掉adapter的连接。
- [ ] 上述7个case每项只运行一次pre-fix，分别保存phase/exit/JUnit/audit。summary跟踪应在“close未调用”断言RED；观测器隔离应PASS；native新增FD断言按实际记录。若native因自然析构偶然无FD，标 `NOT_REPRODUCED_AT_THIS_SNAPSHOT`，不重试，也不冒称新FD失败；原审计与确定的显式close RED仍保留。

### Task 2：最小生命周期修复与有界GREEN

- [ ] 复核连接跟踪确认只指向summary自有连接后，实施上述两层上下文显式close。不得改repository借用连接规则或关闭非自己拥有的连接。
- [ ] 正常/异常退出都close后才返回或向上抛出；成功hash在close之后，COUNT/VACUUM/checkpoint失败不返回假summary。原SQL语义、数据、任务计数和source证据不得为了关闭而改写。
- [ ] 七个case各运行一次post-fix：显式close全部通过；无替身native返回前后本run FD均0；观测器隔离通过；lease=0、heartbeat=[]；source hash与关闭后文件相等；owned进程正常回收。
- [ ] 原生FD仍非空、owner指向repository/worker，或需要动这些层时停止相关修复并提交下一Astra轮；保留当前修复和仍失败状态，不把它们混写为通过。
- [ ] 延续R419其余已批准真实性任务与针对性GREEN。最后合并一次fresh Astra review，审查真实性、指标资格隔离、连接生命周期和旧原件完整性；不重复全suite/full矩阵。

## R419 新测试前置自查补充

允许在下一次RED或新汇总代码实现前，把同一新测试 `_probes()` 的 `recovery["recovered_jobs"]` 从 `1` 修正为 `["recovery-job"]`。实际adapter返回的是 `ArtifactRecoveryService.recovered_jobs` 的job_id列表，原生receipt也为列表；整数只属于新手写fixture的结构失配，不能反推真实产品回执为整数。业务断言/预期不改，原17+4 RED、audit与JUnit完整保留；本计划test SHA仍记录改前输入，新stage冻结改后pins。这是尚未冻结新测试的前置纠正，不新增产品根因、不扩大FD范围，也不为此重复整组旧RED。

## 新路径、次数与运行前置

复用冻结R419 `run_stage.py`，每stage一个精确node，不改它或R413 bounded_stage。该runner仅把导入的ROUND绑定到该stage新preflight pins。所有新证据放在R419的 `validation/` 下，R420报告交叉引用：

- `r420-red-native-fd` / `r420-green-native-fd`。
- `r420-{red|green}-summary-{success|count-error|vacuum-error|checkpoint-error}`。
- `r420-{red|green}-observer-{success|query-error}`。

每个目录排他新建；重名不删除/复用，记录另一个唯一后缀。兼容现有 `R419_EVIDENCE_DIR`，新audit文件独占写入；原red-native/red-projection一字不改。最多新增7个pre-fix+7个post-fix case，零自动重试；pure每node120秒，native每node600秒，owned cleanup30秒。cap不是耗时承诺，也不调整job30秒timeout、leaseTTL或恢复等待。

实施前复核本计划pins。预期R419/R420允许改的adapter/test每stage记录新pins，其余1309基线范围按冻结约束复核；不得把批准修改当意外漂移，也不得无条件更新其它文件pins。使用绝对项目`.venv/bin/python`，只用现有依赖、新DB/basetemp，无共享SIMULATION_RUNTIME_DB、无网络/模型/硬件、无旧DB SQL。超时仅按PID+start_time+scope回收owned树，保留真实exit/INCOMPLETE，不全局杀进程或补造JUnit。

## 验收与停止边界

验收证明的是：adapter自有连接在成功/异常返回前显式close；hash在close后；原生无替身路径在观测器前后均无本run SQLite句柄；观测器自身关闭有独立证据。资源与状态各自断言，不再被早先status FAIL遮挡。

原4FD只能按原audit描述；新数据若只证明summary缺close而未逐项证明旧四FD归属，报告继续保留归因边界。任何新根因、未计划错误、超时、lease/guard拒绝或越出两文件范围先交下一Astra；R419已预期status RED无需重开计划。禁止gc.collect、靠析构/进程退出、删DB、筛掉FD、松guard或延长等待换绿。

本轮规划不声称资源已修复、研究资格已恢复或完整远端复现。实施交付沿用既有Git和本地raw/DB边界；Astra此轮只写plan.md/plan.json。

## 输入SHA256

| 路径 | bytes | SHA256 |
| --- | ---: | --- |
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round420-phase11-returned-sqlite-fd-lifecycle-20261104/intake/observation.json` | 3479 | `3b601ccbf6e6666e82503fbbd8a839f82eb46ef7391194da03347bf89b3b312a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/red-native/native-blocked-audit.json` | 1089 | `361844a8b92103df75c5e5774050e2cb776ce06eeaf4440970643da272ffaff4` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/red-native/result.json` | 398 | `9037dccb1af51c7d47683c3847efbf98aa3eb73171e3c2c63ef3576d8e3cccc8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/red-projection/result.json` | 401 | `e30aa27af307d3f13b5c7ff843e52bf8ce7c372d95743f26a11cd7a45a778927` |
| `src/cloud_edge_robot_arm/final_evaluation/adapters/simulation_runtime.py` | 18365 | `e63c8278ae26015d2aad360cf289a45000c4e137989257e9f20d1aa115769089` |
| `tests/test_phase11_adapter_receipt_truthfulness.py` | 11021 | `4d1dc37910251cc3ed9cf8928e28c2fa289cb80665dc8d4780c5d1fb16219614` |
| `src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py` | 138430 | `6e1ae6471e5d75c195057e1f8e1f90854b1efcfe21f21660bd0a7d75a6d21eb2` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/run_stage.py` | 3173 | `fd82af588f9341da6ef93a6a91bbca3dce11de1ea22b01e70244cd116d0aa69b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/preflight/plan-adoption.json` | 1466 | `aa72f317f759014584fd5f202e21c4bd8dc8210f70cbb1210845377fb9bec1a1` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/plan.md` | 24864 | `2cbd27f4fd9494a262d880257366f971109d82a7339f5bbe55504faec8b41606` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/plan.json` | 35801 | `a6b4994721984d52866b668d54c60f160109583eea8153855498dde4453739b8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/red-native/junit.xml` | 2782 | `17e289180ac1ba01f4ba0b3f29a771fd7bf0def3107d2b8966b34ca8182afaac` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/red-projection/junit.xml` | 11584 | `62a41029411df85bc9d0a1485eb07da87d89fc222ec5c493937baaa0cd604974` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/bounded_stage.py` | 9291 | `d1565de800982ccdc9223b7636a93de0bd99f8aae56131d74ccb8bc320fb085c` |

## Self-review

- [x] 原audit、JUnit、stage退出与源码已静态核对；没有把未执行FD断言说成FAIL。
- [x] 明确返回时句柄与进程退出回收两个观察时点，未推断宿主残留。
- [x] 事实/假设/未确定归属分开，观测器自身影响有独立验证。
- [x] 生命周期修复范围两文件，异常保留/close先于hash/不碰借用连接均可执行验证。
- [x] 新case次数、精确独占路径、cap、停止线与联合最终审查已限定；本轮零行为执行。
