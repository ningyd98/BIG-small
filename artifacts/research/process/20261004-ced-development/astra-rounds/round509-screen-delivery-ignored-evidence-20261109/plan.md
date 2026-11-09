# R509 Restricted evidence Git delivery Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans；用户已授权已验证研发交付，无需重复确认。实际规划者 gpt-6-astra；本轮仅生成计划，未暂存、提交或推送。

**Goal:** 以限定单文件强制加入解决冻结 .pth 证据被忽略的问题，继续 R505–R509 已验证研究 artifact 的独立分支交付。

**Architecture:** 使用独立临时 GIT_INDEX_FILE 从批准 base 构造树，逐文件暂存明确清单；仅一份经字节/SHA审查的 .pth 使用 git add -f。以 commit-tree、带旧值保护的 update-ref 建立独立研发分支，正常 push 并核本地/上游/远端 SHA。

**Tech Stack:** Git plumbing、临时索引、Python 3 文件清单与 SHA256；不修改 .gitignore 或共享索引。

**Spec:** 本目录 failure.json、AGENTS.md 与本轮显式交付授权。

## 问题、证据及根因

failure.json 记录原 git add 返回1：R507 evidence/baseline.before.pth 被仓库 .gitignore 忽略；原始工具错误留在主任务，尚无本轮 branch/commit/push。无需重现失败。98字节文件已读取，内容仅为原 Python site-packages 绝对路径，无凭据、SDK源码、权重或环境内容；SHA256 为 7c6d722cc64172f763eea7587c77feed02217b2a341cb9103f4e887891b1773a，匹配失败清单。该路径证明是冻结研究证据，被扩展名忽略规则阻止，不应通过改字节/改规则来规避。

选择限定强制加入这一份原件；不能由此扩大到其他忽略文件。plan.json 列精确文件路径、允许根目录及输入 SHA。本轮规划曾误读一个不存在的 R507目录名，随后按 failure.json 中真实路径读取并核验；该只读路径笔误未产生文件或 Git 修改。

## 全局限制

只允许本计划列举的五个完整 R505–R509 根目录中的研究文件；目录前缀只是范围边界，不是递归 git add 授权。必须先生成逐文件清单并审查，再使用 NUL 分隔 literal pathspec 暂存。排除 *.local.json、__pycache__ 及其所有内容、*.pyc、*.pyo、嵌套仓库、临时索引/锁、凭据、完整批量raw、运行数据库、权重、SDK及环境。绝不暂存 datasets/、.venv*、任何根目录外文件。

禁止 git add -A、宽泛 git add -f、修改 .gitignore、清理失败日志、改冻结原字节、checkout/reset/stash 当前工作树、覆盖共享索引、强制推送。原失败即便导致临时索引部分暂存也不复用它；建立新的独立临时索引，保留失败记录。

原始 pth 文件只作为文本证据入库，不复制其指向的目录。清单或派生报告不能被描述为完整远端复现包。未完成的候选继续如实标状态，不以本次Git交付代表全部八候选已测完。

## 前置条件与 Review Focus

- 重新核本计划输入 bytes/SHA，尤其 .pth 原件；变更即停止。
- 只读记录 shared HEAD、符号分支、真实共享 index 字节SHA（不存在则记不存在）；批准base为 025c538935199ea7d3aa8cf15b6e93ac9826cf3a，必须存在且确认为当前交付依据。
- 检查目标 refs/heads/codex/ordered-small-vlm-screen-20261109、origin远端和对应远端ref。当前计划期望目标不存在；若已有其他提交，停止并核是否此前本轮已完成，不能覆盖或重写其历史。
- 保留 R505–R508 开发/真实验证证据，确认待交付文件为当前已验证版本。独立进行中的候选文件可能改变：以准备清单的 bytes/SHA 冻结本次交付快照，暂存前后再核，发生变化则重新界定快照，不提交半写文件。
- 检查树差异只含明确允许文件；精确 .pth 的 blob 字节等于原件；共享 HEAD/index 前后一致；push 后三方SHA一致。Git同步不是模型科学验收。

## Task 1 — 冻结交付清单

- [ ] 新增本轮 diagnostic/ 的只读诊断及步骤报告，保留 failure.json。可用 git check-ignore -v -- 精确pth路径记录忽略来源，返回1/0按命令语义解释，不改规则。
- [ ] 枚举 plan.json allowed_roots 内普通研究文件，排除上述路径类型，生成明确逐文件路径/bytes/SHA清单。对符号链接、意外大文件或不明敏感内容停止审查，不跟随链接。清单不把自身SHA循环纳入；可用单独receipt记录清单SHA。
- [ ] 审查清单只含已验证交付及本轮过程证据；精确pth列为唯一 force_add_path。其余发现被忽略的文件不自动force，保留并交新Astra或明确后续处理。

## Task 2 — 临时索引与独立提交

- [ ] 选择未存在的临时索引路径；仅对本次Git子进程设置 GIT_INDEX_FILE，不改 HOME/CODEX_HOME，不触碰共享 index。执行 git read-tree <base> 建立临时索引。
- [ ] 普通文件清单用 --literal-pathspecs 及 --pathspec-from-file/--pathspec-file-nul 逐项 git add；唯一例外单独执行 `git --literal-pathspecs add -f -- <精确pth路径>`，必须仍在同一临时索引。不能传目录或通配符。
- [ ] 使用临时索引检查 cached diff 相对base，路径集合必须等于预期交付变更且没有删除/越界文件；逐一核 index blob SHA256 与清单相等。历史原日志即使存在空白问题也不改字节，不以清理日志通过检查。
- [ ] 执行 git write-tree，再 git commit-tree <tree> -p <base> -F <真实换行提交消息文件>；记录新commit。用 git update-ref refs/heads/codex/ordered-small-vlm-screen-20261109 <newcommit> <全零旧值> 原子创建分支，不切换工作树。若ref已存在，禁止覆盖；先核是否同一已完成commit，否则停止。

## Task 3 — 推送与验收

- [ ] 正常执行 git push -u origin refs/heads/codex/ordered-small-vlm-screen-20261109:refs/heads/codex/ordered-small-vlm-screen-20261109，不 force、不改 remote URL。凭据/网络失败保留原错，不伪称完成。
- [ ] 核本地目标ref、其配置上游ref及 git ls-remote 返回的远端目标ref均等于newcommit。不得拿本地缓存ref冒充远端查询。确认提交树中精确pth SHA与原件一致。
- [ ] 复核共享 HEAD、符号分支、真实index SHA与前置记录一致；如有独立任务并发改变，报告并调查，不reset回去。
- [ ] 写 delivery-receipt.local.json 记录commit/tree/三方SHA、交付清单SHA、共享状态前后核验及本地大raw边界；该receipt按本计划排除远端提交，避免自引用循环。Git交付成功仅在三方SHA核验后声明。必要的预提交步骤报告可随本次提交，事后receipt本地保留。

## 验收与停止边界

开发与实际Lens/Molmo结果沿用其已验证证据，本轮不重跑模型。交付验收是限定文件树、原件完整、共享状态不受本轮影响及正常推送后三方SHA一致。正式研究/heldout/实机验收不因提交而改变。

新忽略文件、目标ref冲突、清单/原件SHA变化、权限/网络新失败、敏感内容、需要扩大force范围或改Git全局策略时，停止受影响步骤并交新实际Astra。不可通过删除证据、宽泛强制加入或强制推送修复。尚未实施时不可声称已提交/推送。
