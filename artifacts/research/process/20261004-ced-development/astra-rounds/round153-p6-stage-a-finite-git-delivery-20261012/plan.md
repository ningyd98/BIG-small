# R153 Stage A 有限 Git 交付 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 按本计划逐门执行；既定 ROOT 负责元数据与交付，不另派产品实施者。

**Goal:** 将已冻结的 P6 Stage A 六源码及有限审计材料交付到既有研发分支，并由 ROOT 作限定软件验收。
**Architecture:** 冻结静态清单与明确派生路径分离；先核终审和依赖，再保存受控状态更新，最后精确复制、暂存、提交和非强制推送。真实 Git 身份收据在提交外本地保存，避免自引用。
**Tech Stack:** .venv/bin/python 标准库 bytes/hash/JSON/XML 与有限 Git；不调用产品。
**Spec:** R113 A / R127 G1–G4 / R134 S-C-F / R151 disposition；精确路径与 SHA 在本轮 selected-manifest.json 及 plan.json。

## 已核事实与边界

实际规划者为 gpt-6-astra，代理 /root/astra_status_plan。R152 独立终审已完成，限定 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO 内 Critical/Important/Minor 均无已确认问题；24/24 只读额度已耗用。终审 JSON SHA db83f79f83f9fd50e56b965949a913da90f7c485776c16f15aa75e7c812b5bf4，外部 authority.files 实为15项，加该 JSON 共16文件。本计划不是 ROOT 已验收记录，也不授予产品变更。

四份实际运行组成40个唯一通过节点：原 GREEN20 保留19PASS1FAIL，R147 修正 foreign 单例1PASS、原 new19 19PASS、R141 CPU positive1PASS；绝非一次40运行。静态证明只支持 R145 类型变更与 R147 夹具变更的有限证据沿用，不等于新增行为运行。正链调用原 episode 后仅注入六 flags，22自然文件 hash 匹配，物理量、模型、动作证据仍为零。精确最终 COMMIT 后失确认故障没有实际运行。B9 公开确认与 SQL 历史区别明确未解决；B/C/D、完整P6、native/physics/actual/formal 均不提升。

740个既存文件19,732,316字节已逐项核对，另外50条两树依赖及6条交付底座共846项全匹配。静态清单保存206个同字节省略映射，排除9个额外历史源码副本；不可将清单或源索引称完整远端复现包。原失败、旧摘要与真实捕获缺口均保留。规划期 Git/产品命令均0。

## Global Constraints / Review Focus

- 主树保持原 dirty 状态，禁止 reset/stash/checkout/rebase/clean；主树 index 不写。
- 交付底座必须在真实前置门复核：分支 codex/research-20261007-p1-delivery，本地/上游/实时远端均 cb59be66fe281d7ee2c1ca90bc803c3b80f37c76，工作树与暂存区干净。该值此前仅已报告，规划未运行 Git。
- dependency-preparation.json 的50依赖逐文件一致，六 owned 底座分别符合 R113 四旧文件与两新文件不存在；漂移不自动扩产品范围。
- 防并发覆盖：受控三文件写前保存 before 并即时复核；复制前与提交前重新核 HEAD，推送前核实时远端。
- 防额外载荷：仅740静态路径加 plan.json 列出的19精确额外路径，共759路径；拒绝 symlink、gitlink、路径穿越、额外文件、删除和重命名。
- 防验收夸大：B9、legacy UTC veto、CPU注入、四run与原失败必须在 ROOT acceptance 与新增当前状态段显式存在。
- 防自引用：最终 payload-index 不给自己和 delivery-paths.txt 写 SHA；两者真实 SHA 由提交外 precommit/postpush 收据绑定。提交内不写本提交未来 SHA。
- 防隐式测试：不执行 hooks、AST/import/compile/collect/static/pytest/SQL/probe；遇活动提交 hook 停止，不用 --no-verify。
- 新失败先保存并交下一轮 genuine Astra；不复用或重置任何已耗产品/终审预算。

## Task 1 — ROOT 输入与限定验收门

- [ ] 全文读本计划与 R152 终审，复核 plan.json anchors、740静态输入、六当前终态源、53保护项和50依赖。
- [ ] 把 ROOT 已保存 b5056b 的真实结构化结果写 root-final-review-check.json；实际15外部 authority 条目，不伪造独立stdout/stderr。
- [ ] 保存 input-check.json/root-activation.json；完成真实 Git 初始前置。所有命令与次数在 plan.json.git_budget。
- [ ] ROOT 决定并新建 acceptance.md/json，仅允许上述 Stage A 软件上限；没有合格决定则不执行后续状态与交付。

## Task 2 — 三文件受控更新和稳定载荷

- [ ] before文件字节完整保存于 implementation/before；当前 SHA 必须与 plan.json.metadata_update.before 相等。
- [ ] STATE仅修改 plan.json 列出的 current_P6_stage_A 当前摘要字段及新增 planning.R153；屏蔽允许字段后 JSON 全等，旧各轮历史与预算不动。P6_complete=false，B_C_D=NOT_ACTIVATED。
- [ ] PHASE与旧状态文档仅在原完整字节后追加 2026-10-12 当前 A 段，明确该段覆盖旧正文的 A待执行表述；原正文、原历史 Git SHA与其他任务均不改。Git仍记待交付。
- [ ] 新建 update-report.json、step-report.md/json，分别记录 before/after、验收范围与准备完毕/推送待执行，不伪报交付。
- [ ] 创建 payload-index.json 和 delivery-paths.txt，以本轮完整精确路径并集为唯一载荷，所有实际新文件才读取真实SHA；不扩大候选。原同字节映射必须能解析到保留项，否则明确本地源快照省略，不能声称远端路径存在。
- [ ] ROOT新 metadata/copy/audit脚本仅可保存到 plan.json.execution_metadata.allowed_scripts；执行前全文读与 pin，均本地不交付。六有限阶段各一次，不隐式调用产品。

## Task 3 — 精确复制、暂存与审查

- [ ] HEAD复核后，按精确路径列表复制字节，拒绝不相容既存目标；核每个目标SHA/bytes/可执行位，50依赖不变。
- [ ] 一次 git add --pathspec-from-file=绝对NUL文件 --pathspec-file-nul；严禁 add . / -A。
- [ ] 实读暂存路径/模式、全blob字节与完整diff，对照最终载荷。仅允许预期A/M且无额外项。
- [ ] 全载荷 diff --check 保存实际结果。不可修改旧证据消除空白；只允许已冻结历史证据逐项例外，记录路径角色SHA行号及行字节SHA。
- [ ] 当前六源码、全部R153提交文件及三状态文档的严格 diff --check 必须 exit0。出现新问题停止，不运行 formatter 修补。

## Task 4 — 正常提交、推送与提交外收据

- [ ] 复核交付HEAD仍旧base；正常 commit 一次，禁止 amend/绕hook。提交消息 feat: deliver bounded P6 stage A lease foundation。
- [ ] 实时远端仍base才正常非force push 一次。不得把并发新head静默当作新基线。
- [ ] 本地HEAD、上游SHA与实时远端SHA必须同为刚创建commit；交付树干净，主树index与无关dirty原件保留。
- [ ] 保存本地 postpush-receipt.json，记录真实命令原件、最终路径数与字节数、三SHA、selected包边界。此文件与Git日志不再追加到当前提交，不产生第二次提交或自引用。

## 有限额度与停止

精确 argv、时序及次数见 plan.json.git_budget：Git最多28次（含前后读取、一次stage/commit/push），产品/新终审/重试额度均0。core.hooksPath未配置exit1，以及全历史载荷空白检查的已逐项匹配诊断，是预定义观察结果；其他意外失败都保留并停。元数据不能代替真实Git交付；Git成功也不能提升研究/物理验收。本轮仅规划，等待 ROOT 实际核对与激活。

