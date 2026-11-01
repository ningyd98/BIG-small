# R383 当前工作区 GitHub checkpoint 交付计划

> **For agentic workers:** 使用 superpowers:executing-plans 按本计划执行；用户已授权整理、提交与推送，沿用现有研发分支，不重复请求确认。无需新 worktree 或 PR。实际规划者为 gpt-6-astra，agent /root/astra_delivery_plan。

**Goal:** 保留当前研究现场，以精确清单提交已验证源码/测试和必要研究记录，完成 GitHub checkpoint 推送及三方 SHA 核对。

**Architecture:** 先冻结并分类当前文件，再做两组有界 CPU 回归，按字节清单 stage、正常 commit/push。旧失败和未完成计划随交付如实公开，完整批量原件留本地。

**Tech Stack:** Git、现有 .venv/bin/python、pytest、标准库；不安装依赖。

**Spec:** AGENTS.md、input-audit.json、既有 git_delivery_20261005.md 与 t12-git-delivery-20261008.md。精确输入哈希与完整运行 argv/env 见 plan.json。

## 问题、原始证据与适用性

当前 HEAD 28ac315c2af8567b377e6e2cc3ee5acb9cda4677，research/20261004-continuation；intake 报告上游和 live remote dd9df375e1d372490145327bcbfee5804352fcc4，领先两提交。本规划静态确认 HEAD 及三个 tracked 源/测试改动、两个仅内部 dirty 的 gitlink；不把父代理提供的网络观察冒充本席再次联网核验。

initial-inventory 有约21475未跟踪文件、2169879950字节；原始状态和清单分别 SHA256 ee74fc15f71a3a79cc11f86e5ee654c74d1e3e0ac538e765fbbbaea9671abcfd、580e713426cc4d1d8c09d6ad83342d585bf8ac6bd68efd8b3751c710cfdf8561。input-audit SHA256 6c2ccf12695468e572b2d88c81318c76c880e8d069d8c7435f3eab183d340d3e，全部列出 pins 本席复核一致。这个问题是交付积压；没有授权借整理之名继续产品修复。

R365 copy 严格语义和 R367 SHA/26 codec 曾有局部 GREEN；R367 原 UTC 双 backend 600秒 NONCOMPLETION 不抹去。R376 原五长节点4通过、commit_close失败，terminal-handoff 引用原 stdout/JUnit/诊断；R380短合同和confirm_timeout通过，独审APPROVED_R380_TEST_SCOPE；R381线程归属修复尚未实施。R377/378/379仍待执行，R382仅旧浏览器准备证据隔离，不能称 browser PASS。

本席一次 sed 路径猜测错误退出2，原工具chunk 29a6b6保留于会话，未提供落盘原stdout；plan.json诚实记录转述及实际Astra行政处置。随后仅用rg发现真实round377-browser-draft-input-contract-20261101路径并固定SHA；未运行或修复程序。长工具输出截断不是完整读取证明，关键diff、短测选择及报告另作有限定向读取。

## 全局约束与审查重点

不修改现有src/tests字节；本轮仅验证、整理和交付当前checkpoint。不重置或清理两gitlink内部改动，不更新其HEAD，不配置ignore=dirty。不得改旧日志、原raw、DB/WAL/SHM、冻结源码、旧账本或历史验收。不可reset/clean/amend/rebase/force push/gc/prune。

审查五重点：公开库误传凭据；批量raw/DB/权重/SDK混入；小报告引用仅本地原件却宣称完整复现；冻结日志空白触发diff检查被擅自“修好”；未完成T3/浏览器被短测与checkpoint掩盖。以分类清单、secret扫描、依赖标注、原件hash及限定结论分别验收，不为这些行政检查新增产品测试。

## Task 1：实施前冻结与分类

- [ ] 复核全部pins、HEAD/branch/上游/live remote、index原状态；核对两个gitlink HEAD与原值相同、仍有内部dirty；核实无并行测试/写源和真实权限。仅新增R383交付文件、计划明确的新总结不算异常漂移。
- [ ] 在R383/preflight保存事实、当前diff及各有效src/tests overlay的SHA；不得递归恢复历史祖先门禁。运行前核对现有解释器、pinned driver/plugins、R196 seed与legacy goldens可读。
- [ ] 对每个intake文件记录 selected/local-only/blocked、精确path、size、SHA256、category/reason。凭据不读取/发布内容或值；只记录路径及排除理由。候选manifest可分片，原始7MB inventory/5MB status可留本地，但发布逐项分类和总量的一致性证据；清单自己不冒充载荷。允许将初始完整清单/状态另作无损gzip交付，必须验证解压后bytes/SHA等于原件，不替换原件。
- [ ] selected 包括三份既有src/test修改、四份新测试；已完成文稿最终版与必要源；小型计划/报告/脚本/失败stdout-stderr-JUnit及来源收据；必要原件小型冻结文本与明确测试fixture。报告通常≤2MB，较大最终PDF/PPTX、必要冻结源或审计清单可逐项说明例外。旧日志有秘密或过大时保留本地并公开原因，不改原件。不能仅凭扩展名将所有JSON当报告。
- [ ] local-only包括完整批量raw、运行DB、环境/缓存、模型/SDK/凭据、重复runtime快照、临时浏览器输出和可再生渲染页面。源证据真正独有且必要的小型部分应显式挑选，禁止忽略整个astra-rounds。无论选入与否均不删除现有文件。

## Task 2：两组fresh有界软件回归

plan.json 给出完整新argv/env，复用原样pinned R377 bounded_stage.py并生成R383新spec。不是重启任何旧runner。统一新360秒总墙钟、串行、无重试；第一组180秒，第二组60秒，每组另留15秒清理。阶段目录须全新，避免pytest --basetemp清空旧原件。记录实际invocation/env/解释器、stdout/stderr/JUnit/events、prerequisite、退出耗时、进程身份/清理和源前后hash。

- [ ] temporal_cpu：copy_dispatch、sha_contract、decode_memo、projection_closure、promotion_bindings五文件，预期1+31+26=58通过。历史26 codec约14秒，适合180秒CPU限额；不跑任何UTC/worker完整生命周期。
- [ ] fixture_diagnostic_cpu：fixture_contract与diagnostic_contract两文件，加rgbd_runtime_control中的test_cancel_racing_failure_converges_every_record_to_cancelled及test_closed_loop_verification_failure_cannot_finish_succeeded，预期3+3+3=9通过，60秒。此选择与R376 shared smoke相同，禁止启动closure全文件或commit_close。
- [ ] 两组均需exit0、准确选择/数量、0 fail/error/skip、accepted prerequisite、源未漂移、已reap且无剩余归属子进程。不需要全仓测试、browser、模型、硬件或真实仿真。核对环境无继承SIMULATION_RUNTIME_DB/凭据，输出DB全部R383独立目录；真实运动禁止。

## Task 3：交付树、隐私与字节校验

- [ ] 检查三份代码diff仅为已计划copy/SHA与R376/R380fixture/诊断改动，不能把checkpoint当R381修复。必要依赖在tracked树或selected中；仅本地依赖逐项标注，绝不承诺换目录clean clone可完整复现现有绝对路径测试。
- [ ] 对selected及两ahead commits的新blob做secret/path/size扫描，仅输出候选路径/行号/类型，不回显值；排除DB、权重与SDK，拒绝symlink越界、绝对路径/..歧义。单blob≥100MB阻止选入，较大文件逐项报告，不新加LFS规避边界。
- [ ] 严格检查新写报告/源码的git diff --check；冻结原件/日志的既有空白问题按精确path/hash分列，保留完整check退出码，不能宣称全diff零问题。所有selected文件与index blob逐项hash/size/mode匹配，原件before/after一致。
- [ ] 可选用.git/info/exclude整理已审local-only生成物：先保留其原内容/hash，追加带R383注释的锚定且转义的精确路径；仅当整个叶目录逐项均审为生成物时允许目录规则。不得隐藏src/tests/计划/未完成代码/作者报告，不改tracked .gitignore，不用assume-unchanged/skip-worktree。该local管理文件不stage；变更与排除清单写入R383报告。两个gitlink仍显示dirty是正确结果。

## Task 4：checkpoint提交、推送与报告

- [ ] 新写R383/step-report.md和phase-summary.md（或向已知权威阶段总结窄追加），清楚区分历史运行、新67项限定软件回归、真实运行0、正式研究验收未完成。R367 NONCOMPLETION、R376 commit_close FAIL/R381未实施、R377/378/379待执行、R382仅准备必须显式保留。
- [ ] 以NUL-safe且literal路径清单git add，审查cached diff/name/status、index总路径/字节、无gitlink变化及无未审核路径。可一份连贯checkpoint或源码测试+文稿证据两提交一起交付，commit message明确checkpoint。
- [ ] 正常push origin research/20261004-continuation，用户已有授权，无需确认/PR。推送后核验本地HEAD、upstream、git ls-remote实时远端完整SHA一致，保存原push输出。远端divergence/传输失败不force、不自动merge/rebase，交下一Astra轮。
- [ ] 若需持久保存首次push收据，新增小型receipt提交再push；最终SHA在外部当前回执及最终答复记录，避免无限“记录自己的SHA”提交循环。明确本地未交付路径/体积及两个gitlink dirty，不能声称全工作区干净或完整远端复现包。

## 失败处置与验收边界

本轮没有预期RED；任一新测试失败、collection error、timeout、source drift、secret/path风险或意外Git失败，都保留原始输出并暂停相关动作，由实际Astra另定下一轮，不在R383顺手修源码、格式化或延时重跑。独立安全的证据/文稿工作可继续，若只能交付证据则明确其有限范围；未通过软件门槛的改动不标为已验证。

本计划明确允许两组限定回归通过后提交当前局部软件已验证的checkpoint，不要求研究全完成、不要求先修commit_close。软件和文稿交付、真实运行、正式研究验收分别记录。本席只静态读取并写plan.md/plan.json，未运行测试、产品导入、stage、commit或push。

父代理补充只读审计：两ahead提交约1307差异路径/16.94MB，未见>10MB或DB/key/weight文件名；初筛小型证据约1083份/73MB，仍须逐项审核而非直接许可全选。两gitlink HEAD均与树内原ddbeb92a前缀一致，缺少.gitmodules且内部历史缺失文件保留。此为父代理报告，本席不冒充独立重跑。
