# R136 — terminalization 补丁文本恢复

实际规划模型：gpt-6-astra；规划者 /root/astra_status_plan；2026-10-11。状态：计划冻结，待 ROOT 输入复核及激活。同一 sole writer /root/p6_stage_a_sol replacement GPT-6.1-sol 实施。规划阶段仅项目 .venv 标准库文本、JSON、字节哈希读取；没有编辑产品或运行产品验证。

## 问题与完整原工具证据

原件目录：
/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round134-p6-red-interface-connection-recovery-20261011/implementation/stopped-patch/

已独立完整读取 patch.txt 和 raw-tool-result.txt。原补丁中新增行 `+        *, phase: str = "REVOKED",@@` 将下一 hunk 的标记粘在代码行尾。原返回为 apply_patch verification failed，期望签名参数行后直接出现 durable_phase 行；当前真实函数之间还有签名闭合、owner 检查及 target 构造，无法匹配。工具报告 Script failed，没有 subprocess exit code、独立 stdout/stderr；这些字段应维持 null/未提供，不能虚构 exit 1 或标记产品/pytest 失败。

原补丁 SHA256：734279b3a12be5435e5ac9d2e9beaa484ca36a10f0aed051f6b7465cab1772c0。
完整工具返回 SHA256：6021554b0d333cbac53f37fd285c15101b3128e6ccd82838ffd8aef3ca0cc554。
finding SHA256：e0f9481b063c9bd47cda0ee1e9e11d19e188193dd9fcd75863a26ceccf96e6e8。
原失败未应用任何补丁字节；当前源与失败后六源冻结逐字节一致。失败前 G3/G4 核心、G1/C 主体和 S/F 测试的中间修改保留，不能回滚为 R134 初始源。G2/publication 尚未完成；本计划不宣称任何中间实现正确或已通过验证。

## 独立根因与限定恢复

当前 sqlite_repository.py 第 1611–1637 行 _terminalize_operational 的真实上下文已只读核对：方法仍无 phase 参数，target 固定 REVOKED，WHERE 包含 lease_id/row_revision/generation，尚无 proposed_row_digest 条件。原失败补丁的四处意图在当前上下文均仍未应用。本轮根因是补丁 hunk 边界/上下文封装错误，不是已经运行发现的 Python/SQL 行为缺陷。

只允许同一作者重新编写该局部补丁文本：
1. hunk 标记独立成行，签名/target/SQL predicate/绑定 tuple 各自带真实当前相邻上下文，不能把不同位置误连成连续旧行。使用结构化 apply_patch；不把 patch 或命令文本嵌套进 shell heredoc。
2. 保留原已授权的负终态 phase 意图：默认 REVOKED、orphan 的 TERMINATED 经既定 G2 路径处理；不能通过该恢复引入任意正向 phase、success grant 或新公共权限接口。既有 owner/connection 验证、真实事务边界和 epoch 撤销保留。
3. 保留精确 digest CAS 意图：WHERE 同时匹配原 lease_id、row_revision、generation 和 proposed_row_digest；新增占位符与原 before digest 参数一一对应，target 的最终 phase 字节参与原 canonical digest。保留 rowcount != 1 的 fail-closed 行为，不扩大 SQL 目标或允许 CAS 失败后补写。
4. 本轮只恢复失败补丁，不重做整文件替换、不覆盖已有中间修改。随后继续原 R127 G1–G4 与 R134 S/C/F 的剩余 G2/publication 等工作；跨多个已授权文件的剩余语义由原计划授权，本轮不增加技术范围。发现新的根因或实现需求超出原范围时停止相关部分，再交实际 Astra。

这不是新 terminalization 设计，也不是修正测试来使检查通过。未完成的原 G2 orphan/finally 等必须继续，不能将当前 COMMITTED-only 查询等中间状态当验收终态。

## 输入与实施前置

JSON 保存 82 个有限输入的完整绝对路径、bytes、SHA256。独立核对 source-index 和 supplement-index 全部已列文件、六对 current/snapshot 与 52 protected pins，共 81 个比对，零不匹配。未把 60KB before-after.diff 的存在/哈希当作全部语义已审查或软件已通过。

关键当前源：
- operational_lease.py：7adb69bfcb286a35b523ac7009bcc0343569802e06c8ac29930533973a40504a
- sqlite_repository.py：dfc2b07cd0df1df04f1578fb91658954c79ee326aa717d05009045f74290299f
- test_operational_runtime_closure.py：f320b83bc1072771b3e22cfacac7b33ffcd1658289d776fe46b4c95cd29302e7
- repository/worker/recovery 仍为 R134 初始字节；完整 SHA 见 JSON。

ROOT 激活前须复核本轮计划和 current/snapshot、52 protected、R134 原激活及当前账本。R134 初始六源 pin 已被授权中间编辑正常更新，不可要求恢复旧字节；只保护本次冻结和未授权路径。若 current 与本轮 pins 不符，先查明是否新并发修改，不自动覆盖。

## 实施与文本核验顺序

1. ROOT 保存 input-check/root-activation，明确同一作者恢复。本计划保存不自动激活产品。
2. 作者保存新 candidate patch 文本，不改原 patch.txt。执行前仅读文本核对：每个 @@ 独立、每一删除/上下文行属于当前目标函数、四项改动对应原意图、SQL 占位符与 tuple 次序一致，owner/CAS/负终态边界保留。这是文本自查，不能运行 AST、compile、git apply --check、probe 或把工具重试充作验证。
3. 应用正确新补丁；只读字节/局部文本差异检查实际变化属于该补丁，保存工具真实返回和 before/after SHA。若工具再次拒绝、出现意外范围或新异常，保存原件并停；不反复重试。
4. 接续原 R127/R134 剩余实施和 source/fixture/proof 冻结。完整继承 R134 精确命令、顺序与 ROOT 门禁，不给本轮新增产品命令。
5. 生成 R136 步骤报告并以追加记录汇入阶段总结，保留旧 failed/partial 历史。ROOT 根据新源和证据复核后，才按既有门禁推进。

## 预算与验收边界

R127 RED23 已 used 1 / remaining 0，禁止重跑。R127 formatter、scope_proof、Ruff 均 used 0 / remaining 1，沿 R134 原激活及顺序使用；不能增加次数、重置或先于剩余实现完成而浪费预算。R134 recovery3、R113 format_check/mypy/GREEN20、R127 new_GREEN19 均继续 held；各 exact argv、cwd、env、证据路径和上限见 R134 plan.json，全部不变。

新产品/AST/import/compile/collect/probe/static/Git/actual/native/model/GPU 预算均为 0。无新用例/节点或 SQL fault probe。仅有界元数据读/hash/JSON 和本轮计划/receipt 写入。验收首先是正确补丁应用且仅原意图变化、旧失败保留、继承预算不变；不会据此宣称 Stage A 软件通过。后续开发验证、实际运行、正式研究分别记录，保留 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO，B/C/D/native/actual/formal 不晋升。

## 本轮元数据路径

允许新建本轮 input-check.json、root-activation.json、executor-brief.md、candidate-patch.txt、patch-text-review.json、implementation/（工具返回、before/after pin/diff）、step-report.md/json、validation.json、phase-summary-addendum.md。只保存派生记录，不覆盖原失败/旧计划/旧 raw。后续交接始终完整绝对路径加 SHA。

