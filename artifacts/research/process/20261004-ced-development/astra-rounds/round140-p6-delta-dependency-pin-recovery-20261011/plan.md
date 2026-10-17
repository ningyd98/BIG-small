# R140 — 未执行 delta 脚本的单项依赖 pin 恢复

实际模型 gpt-6-astra；规划者 /root/astra_status_plan；2026-10-11。冻结待 ROOT 激活；同一 sole author /root/p6_stage_a_sol 只修元数据脚本。

## 问题与独立核实

原发现及脚本快照位于 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round139-p6-test-capture-lint-repair-20261011/implementation/stopped-script-input-review/。finding SHA256 2593f597af58b7334b510a9966e94abf271baeadec8f1f20ca29e9dd8ecca0a4；source-index SHA256 89505071765cc708cc384f811f44d0132b11b55362c3959e26142860676906cf。

独立全文阅读未执行 delta-proof.py：113–119 行列五个 dependency_paths，122 行直接 pins[str(path)]；pins 只来自冻结 R139 plan.inputs。标准库 JSON membership 核对显示唯独原 R127 implementation/scope-proof.py 缺失，其他四项均存在。R139 pin 了冻结副本但未 pin 此原路径；内容同哈希不能让不同 key 自动等价。

缺失依赖实际当前文件：
/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round127-p6-private-authority-lifecycle-repair-20261011/implementation/scope-proof.py
bytes 7714；SHA256 2fbff6a9b43ab829245f7e09370eb392e607b4af17b9c63dcfd6ef7e21b13983。已真实读字节核对，符合既有冻结副本。未运行该脚本，未发生 KeyError/traceback/exit，不得伪造运行失败或 raw 输出。本轮是执行前元数据合同缺口。

## 唯一修复方案

保留冻结 R139 plan.md/json 原字节和 PLAN_SHA 检查。只修改 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round139-p6-test-capture-lint-repair-20261011/implementation/delta-proof.py：
- 增加一个命名明确的 ORIGINAL_SCOPE_PIN 常量记录，path/bytes/sha256 必须逐项等于本计划上述值。
- 依赖循环只对 str(path) == ORIGINAL_SCOPE_PIN['path'] 这一精确分支使用该常量；其他四项仍严格 pins[str(path)]。禁止 .get 默认回退、glob/相似叶名查找、任意缺失路径 fallback、动态信任当前哈希或批量扩充旧输入映射。
- 所有五项仍执行 pinned(path, bytes, sha256)，依赖列表不得删减。输出该单项的 pin 来源为实际 R140（可在独立 provenance 字段记录），其他记录仍来自 R139。新常量不是旧计划曾包含该路径的证明。
- 不改 callback/AST 归一、comments/constants/39 IDs、五生产/53 protected 检查，不改结果写入位置或 exclusive create，也不修改 runner/旧证明/测试源码。不得用删除依赖检查来使脚本继续。

原脚本 draft SHA f50a47671a1c539b8907b78eb91bbee7fe3b35cd2b33d1a22c6ede373f1d9bbf 原样保留。该唯一 metadata 修正完成后，ROOT 必须实际文本复核新脚本与局部 diff、确切常量及依赖循环，才能按原 R139 门禁推进。

## 输入、边界与实施前置

JSON 保存 26 个有限输入完整绝对路径、bytes、SHA。冻结索引的七 current/snapshot 对及 finding 共 15 项比对均匹配；源于原脚本的五项 dependency membership 仅一项缺失。R139 MD/JSON、activation、作者/ROOT ledger、原 proof、runner、before/manual-after/manual diff、当前测试与只读 ROOT receipt 都作为依据，未执行 AST 或产品。

当前测试 SHA b53a817ad0bd4c46ca8df271e549a31f1ef66e8f09fd77dedcf0b4ece9031e30，65111B；其三个 kwonly defaults 和注释换行是已授权 R139 手工修改，不能把它相对 R139 初始 hash 的差异当未经授权漂移或回滚。R140 不进一步编辑测试。五生产/53 protected 仍由 R139 固定，本轮不扩大它们或新增产品语义。

ROOT 激活前核 26 pins、原 missing dependency 的真实 bytes/hash、作者与 ROOT 账一致。若该依赖改变，停止，不更新常量迎合新字节。输出计划本身不解除 delta gate。

## 次序、验证与原预算继承

1. ROOT 有界 input-check/root-activation；同一作者保存原草稿不动，修正唯一 metadata 脚本并保存新的局部 diff/after-script pin。
2. ROOT 实读完整新脚本、runner 与本轮 delta，确认只做精确 pin 分支和来源记录，所有原验证仍在。此阶段只允许标准库文字/JSON/hash 核对；不得 AST parse、import/compile/collect 或偷跑 proof。
3. 按 R139 原 exact argv/env/cwd/输出路径顺序 test_formatter → delta_proof → test_ruff，各继承 used 0 / remaining 1；没有新增、重置或额外试运行额度。delta 仍须 ROOT 文本审批后才可运行；本轮不改变原 runner。
4. 新问题/计划外失败保存后再交实际 Astra，不修改旧 plan 或自增重试。原 RED/static 均已耗尽，recovery3 与四终门仍 held。ROOT 的独立产品 source/fixture/proof 审查可继续，不受此元数据修复干扰。

新增产品/测试/static/AST/probe/import/compile/collect/Git/native/actual/model 额度全部 0；R139 原已授权 delta 的单次 AST 证明仍只在原执行时发生，不提前执行。本轮验收仅为依赖元数据查找完整且不弱化检查，不是软件/真实运行/正式研究通过。

## 允许元数据输出

本轮可新建 input-check.json、root-activation.json、executor-brief.md、implementation/（新旧脚本 pin、局部 diff、文本 review）、validation.json、step-report.md/json、phase-summary-addendum.md。唯一允许修改的既有文件是上列 R139 delta-proof.py；所有旧计划、原发现、快照、runner、产品/测试保持原样。后续交接使用完整绝对路径加 SHA。

