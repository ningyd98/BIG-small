# R145：P6 mypy 类型契约限定修复

实际模型 **gpt-6-astra**；规划者 /root/astra_status_plan；2026-10-12。冻结待 ROOT 适用性复核与激活。规划阶段未运行任何产品验证或 AST。

原 R113 mypy 已真实单次 exit1：22 errors / 2 files；完整 4504B stdout SHA256 172c0ca567b9db0cb6157426d376f1dc9141473d8f020b86050c394266ffd6f9 保留。原 format_check exit0 与 mypy exit1 均已耗 1/0，不重置。JSON 逐条保留22诊断、全部109个绝对输入SHA/bytes与精确命令。R146 修复的是独立元数据汇总传输问题，单次 e7aaeb exit0 后103pins/92对照全匹配，六源与冻结一致，53保护文件不变；没有产品运行。

## 独立根因与两源范围

- **T1（诊断 1,2）** Always-raising __reduce_ex__ declares incompatible int/object override, while object requires SupportsIndex and return contract.
  允许：Change only protocol annotation to SupportsIndex and return annotation to NoReturn, plus exact typing imports; keep same function name/parameters/body/exception and error string.
  边界：No serialization permitted; body remains unconditional existing OperationalLeaseError.
- **T2（诊断 3,4）** The function-scoped name issued is inferred _IssuedProposal in first loop then reused for _IssuedView.
  允许：Rename only second loop binding and its references to a fresh local issued_view; do not change either registry, loop, conditions or state setter calls.
  边界：Same registry iteration/locking/order and exact object identity.
- **T3（诊断 5,6,7,8,9,10,11,12,13,14,15,16,17,18）** consume branch uses proposal for _IssuedProposal record; other branches reuse proposal for actual LeaseProposal. Python early return makes runtime scopes mutually exclusive but mypy local type inference does not split names.
  允许：Rename only consume-branch record local at _proposal_record and its uses to issued_proposal (or an explicitly recorded fresh equivalent); retain all actual LeaseProposal variables in confirm/propose and all _proposal_record checks.
  边界：Original prior-bound/deadline/epoch/cancel/reply identity checks and request/confirm order unchanged.
- **T4（诊断 19,20,21）** Callable/_Wrapped/contextmanager static interfaces omit genuine Python function __code__/__wrapped__ runtime attributes used for existing private caller authorization.
  允许：Use inline cast(FunctionType, guarded).__code__ for known local nested Python function. For two genuine contextmanager-wrapped methods, add at most one private structural Protocol with only __wrapped__: FunctionType and inline cast to that protocol before the same __wrapped__.__code__ access. Only necessary types.FunctionType and typing.Protocol imports; no runtime_checkable/decorators/method implementation on protocol, no new generic Callable[Any] or Any casts.
  边界：No wrapper/helper extraction, unwrap traversal, getattr fallback/default, manufactured code object, frame depth/name changes, registry/allowlist changes. Attribute expressions still obtain exact original objects once in the same frame. Protocol is type description only, never accepted as runtime permission.
- **T5（诊断 22）** _current_session is explicitly Optional, but nested release comparison directly accesses lease_id.
  允许：At this one existing right operand only, cast(OperationalLeaseSession, _current_session(self)).lease_id, retaining original allowed and job_id == expression and lazy evaluation. No duplicate/eager lookup, fallback fabricated session, new authorization, or None swallowing.
  边界：Concrete cast returns the same value; it does not prove non-None or confer authority. If no session exists, existing runtime failure remains failure; this round must not change that behavior or claim it impossible. Existing session/view/transaction/stack checks remain. Any request to change None handling needs separate behavior plan.

仅可修改：
- /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py
- /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py

其余三生产、整个79032B测试（SHA256 9af4327094f3a12d22d7253b37c1ee9ea030cfacf82ab368e70555c927fd5e9e，原40节点）、factory/P5/53protected 全部字节固定。所有既有 SQL/占位符/参数、字符串/bytes常量、注释文本、异常、事务、权限、epoch、窗口及 legacy UTC veto 不变。不许 type:ignore、noqa、Any escape、关闭mypy、改变配置或删失败。未见需要 runtime 行为修复的依据；本计划不把 Optional cast 当作非空运行证明，也不授予改变缺失session行为。

## 新的最小验证预算

ROOT 激活并全文读实际源码 diff、/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round145-p6-mypy-type-contract-recovery-20261012/implementation/type-delta-proof.py 和 run-budgeted-command.py 后，才按顺序运行四个新的单次命令，各 0/1：

- formatter: `.venv/bin/python -m ruff format src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py`
- delta_proof: `.venv/bin/python /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round145-p6-mypy-type-contract-recovery-20261012/implementation/type-delta-proof.py`
- ruff: `.venv/bin/python -m ruff check src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py`
- mypy: `.venv/bin/python -m mypy --follow-imports=silent --no-incremental --cache-dir=/tmp/bigsmall-p6-r145-mypy src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py src/cloud_edge_robot_arm/simulation_runtime/repository.py src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py src/cloud_edge_robot_arm/simulation_runtime/worker.py src/cloud_edge_robot_arm/simulation_runtime/recovery.py`

cwd=/home/ningyd/文档/ChatGPT/BIGsmall，env=PYTHONDONTWRITEBYTECODE=1 / PYTHONPATH=src:.；各 evidence_dir 为本轮 implementation/对应命令名，均 expected exit0。mypy 使用全新 /tmp/bigsmall-p6-r145-mypy。不存在第五次格式/导入排序/全套旧proof/positive重跑/额外测试预算；新四额度不能补给原已耗额度。

单次 delta proof 只能按 JSON 白名单进行精确 AST 归一化：一个拒绝序列化签名、两个指定子树局部变量改名、四个精确 concrete cast、一个仅含 __wrapped__:FunctionType 的私有 Protocol 和必要类型导入。必须拒绝宽泛擦除所有 cast/annotations 的证明。归一化后整个两模块 AST 相等，既有 str/bytes 常量（含 SQL UTF-8）及注释 token 文本相等，所有现有函数名/参数形状/调用顺序/frame鉴权不变；其余源与测试/保护文件全hash相等。不要运行旧proof或声称旧proof自动适用于任意新语义。新增 descriptor 只表达类型，不能变成权限接口。

四命令成功且 ROOT 实读新源/delta/raw 后，才释放原 GREEN20→new_GREEN19，各0/1；JSON 从真实账列出原 exact argv/cwd/env/basetemp/JUnit。任何失败或新根因均保留后暂停，另立实际 Astra，不原地补修重试。本轮无需新增 positive，因为限定运行表达式不变且已有真实CPU positive；若无法证明此边界则停止另规划，不自动扩大。

## 账本与历史

实际耗用依据为原 result.json、R113 author ledger 与 R127 inherited_commands。R141 inherited_final_commands 的 format_check/mypy 仍保留计划派生旧0/1，但 inherited_gate已HELD，不能作为重跑授权。允许 ROOT 先保存本轮 implementation/root-ledger-before-sync.json，再仅同步这两项耗用字段到1/0、各自实际exit0/1及来源；argv/env/cwd/其它记录保持不变，保存有限字段diff。冻结计划、旧快照、原raw一律不改。

允许本轮 input-check/root-activation/executor-brief/两ledger/implementation/validation/step-report/phase-summary-addendum。执行前所有 pin 与预算仍须复核；新证据目录和cache不得已有旧运行内容，不通过删除清理来制造首次执行。每次真实捕获独立 stdout/stderr/exit，ROOTreview gate不能省略。

验收仍为 Stage A lease foundation with legacy UTC veto。类型检查/软件测试不等于真实运行或正式研究；已有 R141 CPU flags 注入1PASS不是 native/physics证据。B/C/D 未激活；本轮不宣称软件完成。计划交付后停止，等待 ROOT 激活同一 sole author。

