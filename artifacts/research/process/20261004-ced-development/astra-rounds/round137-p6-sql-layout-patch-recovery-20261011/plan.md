# R137 — SQL literal 排版补丁工具恢复

实际模型 gpt-6-astra；规划者 /root/astra_status_plan；2026-10-11。冻结待 ROOT 复核激活。同一 sole author /root/p6_stage_a_sol replacement GPT-6.1-sol 接续；规划未编辑产品/测试，未执行产品验证。

## 独立事实、原因与捕获限制

完整原件目录：/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round136-p6-terminalization-patch-recovery-20261011/implementation/stopped-sql-layout-patch/

独立完整读取原 patch/raw/capture-clarification。当前 sqlite_repository.py 中 open_attempts SQL 在第 1568 行，attempt_row SQL 在第 1572 行；两条原长行仍在，目标拆分形式未出现。原补丁先匹配较后的 attempt_row，再找较早的 open_attempts；工具第二 hunk 返回 Failed to find expected lines，与源码顺序倒置、匹配游标向前的原因一致。本轮恢复只处理补丁排列及真实相邻上下文，不推导 SQL/pytest 行为故障。

原 patch SHA256 f5464eb4d2d2e9ebbcad995503aaec900381b90ab72afd8fc780f0297728fed4；raw tool result SHA256 85c9472582ca4f86d83672806a4d84e635d9de970efe8da3ca625c94407af99a；capture clarification SHA256 203ea2e136ca14ddb653236ecb1ba5b1ad67e575a742aa35d1e39a408963e712。

工具只有完整返回诊断，没有独立 subprocess exit/stdout/stderr。失败前没有恰好对应本次 patch 的整文件 byte-exact snapshot/SHA；只有有限文本读取。故只能说工具拒绝且两处原文仍在，不能声称已由 before/after whole hash 证明全文件零字节变化。R136 validation 仅证明此前局部恢复，不能补作这次缺失的 before。当前六源已真正冻结，后续以本次 snapshot 为起点，不伪造历史。

## 限定方案

这两处长 SQL literal 的拆行可作为已有格式要求的准备，但不是功能修改；未运行 lint，不能声称已观察 E501。允许新 candidate 仅按源码先后顺序 open_attempts → attempt_row 排列，每个 hunk 有独立 @@ 与当前相邻 if/赋值上下文，使用结构化 apply_patch。禁止重放原失败文本、逆序搜索或整文件替换。

两个 SQL 运行字节必须分别完整保持：
- SELECT * FROM simulation_job_attempts WHERE job_id=? AND ended_at=''
- SELECT * FROM simulation_job_attempts WHERE job_id=? AND attempt=?

相邻 Python 字符串拆分处仅把现有空格保留在前一 literal 的尾部；不能增删空白、引号内容、占位符、谓词或参数。(job_id,) 与 (job_id, kwargs['attempt']) 的绑定顺序、fetchall/fetchone、现有 private writer/transaction checks 和所有后续断言均不变。不得添加 SQL 执行探针、AST/eval/import 验证、fixture、权限 mock 或新节点。

若作者文本自审认定无需此次局部排版，可以明确在本轮报告放弃两项修改、保留当前字节并直接接续原自审；这同样不是重新执行失败补丁。不能默默把放弃改称已应用。若选择修改，先保存本次 current whole-source before SHA/快照、新 candidate 与文本核验，再应用一次；新异常停止交 Astra。

## 输入及恢复前置

plan.json 保存 80 个有限输入完整绝对路径、bytes、SHA256。81 项校验全部匹配：原索引文件、六对 current/frozen、52 protected pins、三对 current/frozen ledger。before-after.diff 只 pin，不声称它覆盖缺失的补丁前瞬时全文件状态，也不把其存在当完整语义审查。

G1/C/G3/G4/S/F 及 G2/publication 主体的正常中间修改全部保留；自审与新 proof 尚未完成，不回滚 R134/R136 初始 hash。当前六源的最新 SHA 在 JSON；ROOT 必须核对这些 current pins、原失败证据、52 protected 和预算后激活。无并发覆盖；出现不明漂移先停。

## 实施顺序与继承预算

1. ROOT 保存本轮 input-check/root-activation，明确恢复同一 sole author。
2. 作者做上述文本选择与自查，报告应用或放弃。若应用，保存真实前后源 hash、局部 diff、工具实际返回；可用标准库对已明确拆分的两段纯文本拼接做 bytes/hash 对比，但不解析/执行产品或 SQL。此为有限元数据核验，不是产品 test/static。
3. 接续 R127 G1–G4 + R134 S/C/F 剩余文本自审、writer/SQL 映射、fixture/lifecycle tally、冻结和 proof 生成。只有这些完成后，按 R134 原 exact argv/env/cwd/证据路径运行原尚未使用 formatter → scope_proof → Ruff，各 0/1。
4. R127 RED23 始终 spent 1/0，禁止重跑。R134 recovery3 与 R113 format_check/mypy/GREEN20、R127 new_GREEN19 始终 held，须原 ROOT 新 source/fixture/proof 门禁另行释放；所有次数、上限、顺序不变。
5. 保存本轮步骤报告、验证元数据和阶段追加记录；任何新技术根因、工具失败或范围扩大都再次交实际 Astra。

新增产品测试、AST、import、compile、collect、probe、static、Git、native、actual、paid/model/GPU 预算均为 0。本轮仅恢复局部工具排版流程，不新增功能或验证次数，不改旧 plans/原失败/raw/账本历史。

## 验收边界与元数据输出

局部恢复验收只要求正确应用等字节 SQL 排版，或明确放弃该纯排版，并忠实保存证据；此后原语义实施/审查/验证仍须完成。不能据此宣称软件通过或正式研究完成，保留 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO，B/C/D/native/actual/formal 不晋升。

允许新建本轮 input-check.json、root-activation.json、executor-brief.md、candidate-patch.txt、patch-text-review.json、implementation/、validation.json、step-report.md/json、phase-summary-addendum.md。所有旧证据只读。后续交接完整绝对路径和 SHA。

