# R141 — 正常成功 publication 的 CPU 软件正向控制

实际模型 gpt-6-astra；规划者 /root/astra_status_plan；上海日期 2026-10-12。冻结待 ROOT 激活。同一 sole author /root/p6_stage_a_sol replacement GPT-6.1-sol。规划阶段只读文本/JSON/XML/字节哈希；没有 AST/import/compile/collect/probe/test/static/Git 或产品编辑。

## 已有证据及新缺口

独立读取 protected tests/test_visual_worker_factory.py：episode 第 154–169 行执行真实 during_episode 回调后固定返回 success=False、FAILED、SOFTWARE_FACTORY_ONLY；没有替换为成功的当前39节点可覆盖正常 SUCCEEDED。_cpu_visual_worker 第312行将该 episode 安装到 vision.execution.run_visual_episode；_exercise 第154行 configure 在 factory 安装之后、poll_once 之前调用，可作为唯一需要的软件 episode seam。

R134 recovery3 的原 JUnit 实际 3 项/0 failure/error/skip，exit0，额度1/0；R139 三项静态均已1/0。原两 restart 的 job/runtime_job/attempt/lease/result/evidence_consistency 一致 FAILED、consistent=true 是合法工厂结果，不是新失败，更不能据此证明 SUCCEEDED。

原 finding：
/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round134-p6-red-interface-connection-recovery-20261011/implementation/normal-success-coverage-gap/finding.json
SHA256 327c1f29e4aae096df5c9d72a20776a3340ec46b3737c809be5583abf6f1ef02。
91 个有限输入的完整路径/bytes/SHA 在 JSON；79 项原证据/六源/53 protected 比对无不匹配。未逐个重读 recovery3 整棵 case tree，不将 manifest 冒充远端完整复现。原 failed/static/RED/proof/CPU结果均保留。

## 只增加一个测试，不改现有39节点

在 tests/test_operational_runtime_closure.py 文件末尾新增一个非参数化函数：
test_normal_success_publication_uses_real_operational_authority。
原39函数、helper、imports、decorators及断言保持原样；新 imports/辅助回调全部放在新函数内，避免改变既有节点。总 manifest 变成原39+新1=40；旧 GREEN20/new_GREEN19 argv 不加节点、不重写旧计划。

只使用现有 _exercise(monkeypatch,tmp_path,check,configure=...)；不复制或修改 protected factory/P5，五生产文件字节保持 R139 final-freeze 不变。新 check 在真实 during_episode 时记录并断言 RUNNING、实际 worker/repo/session/job/lease/attempt 对应、attempt 未结束且 lease 未释放、原任务窗口/原 domain 存在。记录 session epoch/lease/原 acquisition/origin 等实际身份供终态对照，不生成新权限、origin 或 token。check 仅观察，不写 SQL、不主动提前切换终态。

## 唯一控制变量：明确标注的 episode 返回

configure 在 factory 完成后取得当时已安装的 execution.run_visual_episode 函数；保存原引用。只在该新测试作用域安装一个包裹函数：
- 原四参数完整原样传入原 factory episode，先真实调用它恰好一次；不得跳过 received/during_episode、runtime建立及 callback。原返回应确为 FAILED/SOFTWARE_FACTORY_ONLY。
- 使用 dataclasses.replace 对这一真实返回仅设置 success=True、status="SUCCESS"、online_reported_complete=True、physical_success=True、failure_reason=None、terminal_reason=None。这六项只是 CPU control 注入，必须独立记录原值和注入值。
- episode_id、所有原零物理量（measured_lift_m/hold_s/placed_stable_s/elapsed_s）、executed_actions=0、model_calls=0、observation_count=0、verification_records 等保持不变。不得伪造动作、图像、量测或native success，不调用现有带虚构动作/量测值的 _successful_visual_episode helper。
- 只允许该 execution seam 的新 monkeypatch；原 _exercise 的 CPU clock seam 保留。不得 patch worker._run/_execute、repo writer/transaction/commit/publication、session verdict/propose/confirm、task semantics 或 consistency checker，不返回常量 VALID，不直接写 SQL 强迫 SUCCEEDED。

独立阅读 apply_s01_task_semantics 第83–100行：task_success 必须合取 episode/online/physical flag、无 terminal_reason、实际 semantics 成功。因此必须如实标明 physical_success=True 是输入控制位，不是物理验证。最终原 result 中该位可以为 true，但旁证必须明确 CPU_CONTROLLED_OUTCOME_NOT_PHYSICS_EVIDENCE，native_physics_validated=false、real_controller_contacted=false、hardware_motion_observed=false；所有报告不能用它晋升物理/正式指标。

## 真实执行与必须断言的正向闭环

一个测试只调用一次原 _exercise/poll_once，实际 worker 的 RUNNING→FINALIZING→SUCCEEDED 分支、private writer owner/transaction、D_lease broker、实际 SAVEPOINT preview/rollback、文件 promotion、最终 CAS/COMMIT/ack/confirm 全不替换。不要额外调用 finalize 或额外执行一次 poll。

在原 poll/finally 完成后，以真实 public repository reads、原 _rows 的只读 SQLite 及原生成文件核对：
1. 同一 job/run/worker/lease，数据库 job.status == SUCCEEDED，attempt 恰好原一个、result == SUCCEEDED、ended_at 非空且 error 为空；lease 恰好原一个且 released_at 非空。与 during_episode 的开放记录形成真实前后证据。
2. 同一 epoch/lease 的 operational row 为 lifecycle TERMINAL、durable_phase COMMITTED、terminal_reason="owned publication completed"，原 acquisition 未改；job_snapshot_json 的 job/attempt 是相同 SUCCEEDED 终态。该实际终态与未修改源码中 finalize→seal→propose→commit→confirm 的唯一成功返回链一起证明经过原权限路径；不以 callback/poll True 单独作结论。
3. 真实 state transition/events 包含合法 RUNNING→FINALIZING→SUCCEEDED 和 artifact_created，不应出现错误恢复/取消来替代成功。无需人为补事件。
4. 由原 worker 自行生成的 job.json、runtime_job.json、result.json、attempts.jsonl、leases.jsonl/lease_history.jsonl、evidence_consistency.json 实际存在且解析成功。逐项核对 DB 的 job/run/attempt/worker/lease 与文件中实际有的字段、终态和时间；不要将不同 schema 强行整对象相等。job/runtime_job/result 为 SUCCEEDED；attempt 行 SUCCEEDED 且已结束；lease 原 identity 已释放。
5. result.task_success、success、visual_episode_success、online_reported_complete、physical_success 为 true 且 terminal_reason/failure_reason 为 None；semantic_success 为 true。task_execution 必须仍 NOT_EXECUTED，模型/动作计数及物理量仍零。这是受控软件成功，不能添加真实运动声明。
6. evidence_consistency 是原运行生成且 consistent == true，所有 status/expected_terminal_status == SUCCEEDED，terminal_event_present/artifact_created_present/lease_released 为 true。对其声明的 file_hashes 逐个从实际 job.artifact_paths 的对应文件重新计算 SHA256、核相对路径落在本用例目录内；不能手写 consistent=true、只检查布尔或忽略不匹配。
7. 没有本次 publication rejection.json/accepted=false 替代成功，也不把 private stage/unconfirmed/backup 文件当 accepted artifact。旁证记录实际最终文件路径、bytes/hash 和 DB 内容；不得改写生成文件以补标记或修一致性。
8. 原 _exercise 证实 session 与两个 owner clocks 关闭，原 factory 的 raw_exit/shutdown 恰好一次，episode/wrapper/received 恰好一次；没有新增线程、重试、second attempt 或后台残留。所有新只读连接使用 closing/finally.close；原 event repository 由 _exercise finally 关闭。需要保留的对象仅用于读取关闭状态，不向已关闭 owner 再读 clock。

新测试另写 software-positive-publication.json 旁证（位于 tmp_path，不覆盖原 publication 文件），包含 controlled_flags_injected=true、注入前后 outcome、原零值、身份/DB终态/文件hash、资源关闭和物理证据排除声明。不能伪造独立 clock/COMMIT 时间线；只记录实际观察。

## 最小预算与 TDD 边界

这是尚无反例的测试覆盖缺口，不是已证明产品 bug。先编写新测试和源范围证明，五生产不动；首次真实 positive_control 预期 PASS，不制造缺模块/故意失败 RED，不重跑旧 RED 或 recovery3。若这个真实控制失败，保留原错误及输出，停止交新实际 Astra；本轮没有产品修复或第二次执行授权。

ROOT 激活后新增四个单次额度，exact argv/env/cwd/证据路径在 JSON：
1. test_formatter：仅测试文件 Ruff format 一次。
2. scope_proof：本轮新 implementation/scope-proof.py，先由 ROOT 全文审阅再执行一次。仅 stdlib 源 AST/tokenize/JSON/hash，不 import/compile/eval/collect/执行产品。证明只追加上述一个 test 函数（内部局部 helper/import）；将新函数节点精确移除后原 module AST/comments/string constants 与当前 R139 final 测试完全相等（位置属性除外）；原39 manifest不变、总40且新节点唯一非参数化。五生产、protected53、factory及只读依赖 bytes 不变；新monkeypatch仅已指定episode seam，无 SQL写/权限替换。原 proof/log/hash 不改。额外依赖必须来自本计划 inputs 精确路径，不猜文件或默认fallback。
3. test_ruff：仅测试文件 Ruff check 一次。
4. positive_control：仅新增节点 pytest 一次，expected exit0/1PASS/0 failure/error/skip/xfail，worker poll 生命周期上限1、episode wrapper/original invocation各1，不加参数化、循环试跑、隐式 probe。ROOT 必须在新静态证明后实际读测试/fixture/proof/runner文本并明确解除这个新用例的运行门禁。

原 R139 三项、R127 RED/formatter/proof/Ruff、R134 recovery3 都已耗尽，不能重置/重跑。新四项任一失败均停、新计划，不改原输入迎合结果。

## 原四终门与独立审查

positive_control 真实通过且 ROOT 独立读 DB/文件/旁证、确认该成功只属 CPU 控制后，再对实际最终源进行原 source/fixture/proof 审查，明确释放原四项：R113 format_check → mypy → GREEN20 → R127 new_GREEN19。原 exact argv/env/cwd/证据路径/次数0/1全部不变。原39行为覆盖由这两旧GREEN完成，新1由本轮单节点完成；不另跑full40。所有其他门仍依原计划/独立审查，不因一个正向控制通过而接受Stage A。

## 实际前置、输入与验收

当前基线测试 SHA 99b85ff009236bdc4c09d878d702b4f42b3754f0596296daf702c96715213eaf，65231B；factory SHA5f99a6bf6e9850875423a5a9eca5f47bbe88e4ff12b97048f218de19b76c57f9 只读。六源及91 inputs由ROOT先核，任何新异常另交 Astra。新命令目录/basetemp必须不存在，不删除旧证据。使用原 .venv、cwd及 PYTHONDONTWRITEBYTECODE=1 / PYTHONPATH=src:.；独立真实保存 argv/env/cwd、stdout/stderr/exit/time/hash/JUnit。生成任务有限冻结，保留 symlink边界，不外追或读取凭据。

新增 native/GPU/paid/model/真实控制器/Git 额度0；没有新物理episode或32episodes授权。通过仅补足“CPU受控成功输入能经真实授权publication形成一致SUCCEEDED”的软件义务；仍保留 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO，B/C/D/native/actual/formal不晋升，负向权限义务仍需原GREEN与独立审查。

允许本轮 input-check/root-activation、executor-brief、command-ledger/root-command-ledger、implementation（before、diff、新proof、四命令真实输出、finite freeze）、validation、step-report.md/json、phase-summary-addendum。后续完整绝对路径+SHA交接，所有旧历史原样保留。

