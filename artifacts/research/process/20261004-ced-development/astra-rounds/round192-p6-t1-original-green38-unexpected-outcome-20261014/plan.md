# R192 — 明确拒绝未知 publication retry schema，保留原失败

实际规划者：`/root/astra_status_plan`；实际模型：`gpt-6-astra`。本文件与同目录 plan.json 是实施前计划；尚未实施修复、未运行本轮命令。所有精确输入 SHA256、节点、argv、环境和路径以同目录 plan.json 的完整字段为准。

## 独立判定

原 R179 GREEN38 实际 child=1、wrapper=2；JUnit 是 37 PASS、1 FAIL、0 error、0 skip。唯一失败为 test_r179_publication_history_getters[local]。runner 在 expected-exit 门停止，原 result 的 JUnit/resource_summary 均为 null，原 resource-summary.json 不存在。原件保持，不追写这些缺失结果。

真实 RecoveryBudget 是不含 schema_version 的旧 plain 模型；VerificationBudgetRecord 的旧解码器已经明确要求 recovery.verification-budget.v1。当前 _publication_body 的 retry 分支却把所有非 exact local schema 都送入旧 plain 模型。未知带标签 envelope 因 task_id 缺失仍被拒绝，但产生了不符合已冻结测试合同的类型字段诊断。这是明确拒绝的分派缺陷，不是已证明的权限绕过；不修改 regex 或用异常包装掩盖类型校验。

R193 已处置的 gate 聚合 KeyError 仍是独立元数据失败。gate.commands 可只含已激活命令，角色账本才记录全部槽。失败聚合不重放、不重造 stdout；本轮后续类型合同审阅是正常只读规划。

## 唯一产品修改

仅 src/cloud_edge_robot_arm/vision/local_temporal.py 中 _publication_body 的 retry 分派。在现有 exact local 分支之后、旧 tagless else 之前，显式拒绝包含 schema_version 但不是该 exact local tag 的 retry 对象，ValueError 明确指出 publication retry budget schema/tag。使用键存在性，不使用 truthiness；null、空值、错误类型、未知 tag 不得落入旧分支。

exact local 分支、tagless legacy strict_retry/_model 分支和其校验保持原字节。生命周期核心、models.py、verifier、其余24 owned、211 protected、两个完整测试文件、七旧正文、A prefix、R175 清理、所有 golden、原脚本/raw/计划不变。若需要范围外变动立即停止下一 Astra 计划。

## 执行次序与独立额度

ROOT 先完整审读本计划和268个初始输入 pin，归档共享源码与四份父账本 before。ROOT 将原 R179 green 的 reserved1/0 正常结清为实际失败；author 原 spent 不改。两轮旧 root_settlement 在两角色视图均标 HELD_SUPERSEDED_R192，仍 used0/remaining1、未执行且不可调用，不能悄悄耗用或重置。

唯一 Sol 写极窄源码变动和本轮新的 prepare-evidence.py/run-command.py；ROOT 只写自己的 root-settlement.py。三脚本及源码 diff 经 ROOT 完整文本/SHA/精确 argv/env gate 后，依序执行四个本轮独立槽：

1. prepare：标准库文本/字节/哈希/JSON/XML，120秒，完整源码范围证明和新候选快照。
2. ruff：仅共享文件 F821/F822/F823，120秒，实际退出0才继续。
3. green51：新的单次600秒验证，冻结原38加冻结原13，51个 disjoint 节点，同一新源码版本、全新路径与槽；任何 skip/error/failure 均停止。
4. root_settlement：新的120秒标准库结算，核完整来源、全51/JUnit/资源/源码范围、旧失败原件和预算历史。

四槽均初始 HELD 0/1；不得重用原 prepare/RED/Ruff/13/38/settler 槽。原 R182 两组分别运行的合同不改；新51只是 R192 独立回归授权，不把旧38失败替换成通过。已有实际回归失败提供修复前证据，无新增 RED。原13PASS只属于旧63ec候选，故新共享源用完整51闭合递归投影与 history 的传递影响。

## 门与证据

新 prepare 用字节证明除批准的显式拒绝插入外全不变；不调用 AST/compile/import/collector。首次读脚本的正常门控不是隐藏执行测试的机会。所有脚本只能使用标准库做约定元数据；runner 只发约定一个 child。完整 launcher 必须 shell-noclobber、env-i、逐参数正确引用，原始工具返回先 store；不能猜 gate 缺失 cmd，不能 parse 带 Warning 的展示文本。

每个运行保存 invocation、真实独立 stdout/stderr、result、tool-return；测试另外保存 JUnit、全部真实 sidecars/temp-index。先保存实际输出再检查 expected outcome。超时必须真实终止/回收进程组，宽限不超过15秒且不是第二次运行。任何失败或路径冲突即停止，不重试。

51节点各自继承一次真实 helper 调用合同，分配实例数量必须从实际 sidecars 求得，不预设每节点4或总204。逐对象核真实 init/close、错误、线程/native线程、四容器清空、方法恢复和 finally。未观测 OS/worker/broker/native/model 计数保持 null。旧失败 run 缺失资源汇总不补造，新资源不倒灌旧候选。

原两历史脚本 archive 和 RED 输入的历史身份保留；新的 consolidated settler 明确分开 historical immutable、current fixed、合法派生 role 状态，不能通过 blanket skip 放松 source guard。所有精确输入和比较规则见 JSON。

## 独审与验收边界

同一 /root/t1_fresh_astra_review 继续剩余8批（原剩3+R179补充5），每批最多600行，不新 seat、不 reset。新验证/结算通过后才续审，原 Needs fixes 永保留。额度不够或出现新问题如实停止。

新计划不授予 T1 通过。当前 T1/T2/T3/P6B9/T12/native/physics/actual research/formal/Git 均未由本轮晋升。只有当前候选实际51、窄静态、源码/资源证明和同一独审闭合后，ROOT 才可做限定 detached-history 软件决定。STATE/PHASE 如需追加事实，须在成功结算后保存 before 并比较并发，不把旧 as-of 字段当当前执行权限。

## 完整机器合同

`plan.json` 保存268项完整 SHA256 输入、两组原节点与新51节点、四条精确 child/direct argv、有限环境、全部绝对证据路径、角色字段处理、前置条件和验收字段。`input-observation.json` 保存本轮实际只读观察、236项源码/保护逐项匹配及真实角色快照。规划结束后停止，等待 ROOT 复核激活。
