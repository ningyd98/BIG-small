# R139 — 测试闭包绑定与注释 lint 修复

实际模型：gpt-6-astra；规划者 /root/astra_status_plan；2026-10-11。冻结待 ROOT 核对激活，同一 sole author /root/p6_stage_a_sol replacement GPT-6.1-sol。规划只读 stdlib 文本/JSON/hash；未执行 AST、产品 import/compile/collect/probe/static/test/Git。

## 原始失败及预算事实

原 R127 唯一 Ruff 实际 exit 1，完整 stdout 4530B，SHA aefeb0d7ee498f0a8a1e45cd82b63378ee32a6fe7ac7ddd9d4f6324b3c0defe3；stderr 空。result SHA c844a8a05c7f3e5ea195bff03f03625a2f503e089f5cb022300f797888260e6e。原目录 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round127-p6-private-authority-lifecycle-repair-20261011/implementation/ruff/，冻结目录 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round134-p6-red-interface-connection-recovery-20261011/implementation/stopped-ruff-r137/，所有原件保持。

独立完整读到 9 diagnostics：B023 source 在 795、809 两处、826；target 在 809、827、854；trial_root 在 849，共 8 条；另 796 注释 102 > 100 的 E501。均在 tests/test_operational_runtime_closure.py，无生产诊断。不将静态失败冒称 pytest 或实际安全场景失败。

原 formatter exit 0、scope_proof exit 0、Ruff exit 1 都已 used 1 / remaining 0，RED23 同样耗尽。当前 ROOT ledger SHA 2ed2de6227fa5841ace594b05524870968f9dafb4655acda3e570cd40946f381 才是实际消费状态；冻结前旧 ROOT ledger SHA 0888ad2b… 留作历史，不能解读为恢复额度。原 source-index 不改写。

原 scope proof SHA cab46a9d91152559689bd472e391764635fa80ee7d7edf083fbb15bc4da68214 是六源 AST/格式范围、53 protected（52 原 + readonly state_machine）、39 source IDs、18 writers 的源证明，不是行为验证。旧证明不改写、不重跑，也不直接宣称覆盖本次新绑定。

## 独立作用域核对与最小修复

冻结测试 788 行 for source,target in trials；每轮建立 trial_root，792 行嵌套 check，795–854 及其 foreign/lambda 使用这些外层循环变量。_exercise 第 145 行实际只传八个位置参数。check 内 foreign thread 在 try/finally join，当前循环使用同步 _exercise；本次没有执行证明存在运行时串轮失效，B023 的实际证据是未显式绑定的静态问题。

唯一代码修复：在这一个 check 的八个既有位置参数之后加 * 和三个仅限关键字默认参数 source=source、target=target、trial_root=trial_root，使定义时绑定本轮对象；八个原位置参数、callback 调用点、函数体、foreign/lambda 及两 trial 的执行顺序均不改。不得用 noqa、规则关闭、宽泛异常、删除 trial/线程/断言、partial 假回调或 no-op 消除报错。variant 是外层测试参数，不是循环重绑定变量，无需额外改动。

796 行注释仅换行，保留原词义：准备动作是实际授权 main-thread status CAS，不是 foreign success。只调整这个默认绑定和这条注释，后续测试文件 formatter 的纯格式变化允许，禁止顺带改测试主体或生产实现。

必须保留两组真实合法挑战 RUNNING→FINALIZING 与 FINALIZING→SUCCEEDED、真实主线程 preparation CAS、身份断言、完整 SQL 前后不变断言、具体拒绝类型、foreign 真线程/join、错误传播、per-trial_root 结构化 evidence 以及原 39 IDs/20+19 边界。五生产源码字节全部固定；publication 设计不在本轮重新设计或验收。

## 输入与前置

JSON 记录 111 个有限输入完整绝对路径、bytes、SHA；96 项比对全部通过，含 31 原索引文件、六 current/frozen 对、53 protected。当前测试 SHA 6bced34545df1e9d733444012ef427e321f07aed83fa3ae16c3fc3f71326abd4（65002B）；五生产和 53 保护文件 pin 见 JSON。大 diff 和 publication-owner-map 仅作为冻结证据绑定，不能据 hash 声称完整行为审查。

ROOT 激活前再核六源/保护文件/当前账本及原失败；若源漂移，先停止相关修复。ROOT 后到原静态审查 receipt 也已作为有限输入，不能解除 held。作者先保存新修改前测试快照/精确局部 diff；不覆盖旧失败、旧 proof、旧原件。

## 新有限验证额度（各一次，非旧命令重置）

仅 ROOT 激活后可按此顺序执行，exact argv/env/cwd/evidence 在 JSON：
1. test_formatter：项目 Ruff format 仅该测试文件一次。理由是增加多行默认参数并换行注释，统一既有 formatter 风格；不得格式化五生产文件。
2. delta_proof：新建本轮 implementation/delta-proof.py，先经 ROOT 文本审阅，再运行一次。只允许 stdlib ast/tokenize/json/hash 对旧冻结测试与新测试作窄范围证明，不 import/compile/eval/collect/执行产品。它应：
   - 验证恰好一个目标嵌套 check 增加三个 kwonly args/default Name，名称与对应外层 loop/trial_root 相同；八原位置参数、vararg/kwarg/decorators/调用点无变化。
   - 先核新增绑定严格符合本计划，再仅在内存中删除这三个新增参数/default，忽略位置属性后，整个测试 AST 必须与冻结 AST 相等。不能删除函数体、assert 或大块节点来使比较通过。
   - 全部原 string/SQL constants 的序列与 UTF-8 字节不变；注释仅指定一条换行，按原词序归一 whitespace 后保持，不能删除/改写其他注释。
   - 五生产文件 bytes/hash 完全相同；53 protected 保持；原39 source IDs/参数化内容与冻结一致（AST 装饰器完整相等＋原 manifest 对照，不 pytest collection）。
   - 原 R127 proof 与 script bytes 不变；形成新的 delta proof，明确它依赖哪个旧源证明、覆盖的精确变化，不能将新参数 AST 说成未经归一的完全相等。
3. test_ruff：Ruff check 仅该测试文件一次，预期 exit 0、无 diagnostics。不重跑原六文件 Ruff；五生产 bytes 未变及旧 raw 没有生产诊断作为组合证据，仍不能宣称旧 exit 1 是全量通过。

任何新命令失败保留实际 raw、消费该额度并停交 Astra，不自行重试/增额。不新增 pytest/测试节点/资源 probe；原 RED/import_sort/whole-proof/旧回归均不得重跑。新三命令都以新目录单独记账，原耗尽的三命令和 RED 保持耗尽。

## 后续门禁与验收

新三项通过后，作者冻结精确最终六源、新 proof、diff 和 raw，ROOT 必须实际读 source/fixture/proof 后才能依原 R134 门禁另行释放 recovery3；原 format_check/mypy/GREEN20/new_GREEN19 仍 held。所有继承 argv、顺序、上限、资源与 legacy UTC veto 不变。本轮不直接释放任何行为测试。

每命令用原项目 cwd、.venv、PYTHONDONTWRITEBYTECODE=1、PYTHONPATH=src:.，保存真实 argv/env/cwd、独立 stdout/stderr/exit/time/hash；新证据目录应不存在，不清空旧证据。计划保存不授权产品运行；实际 native/paid/model/GPU/Git 额度 0。静态修复通过只能证明限定 lint/源码变化符合边界，不能代替软件行为、真实运行或正式研究验收，B/C/D/native/formal 不晋升。

允许本轮新 input-check/root-activation、executor-brief、command-ledger/root-command-ledger、implementation（before、diff、delta-proof.py、三命令原始输出、freeze）、validation、step-report.md/json、phase-summary-addendum。所有交接用完整绝对路径与 SHA。

