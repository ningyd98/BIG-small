# R462 原始证据交付检查计划

实际规划模型：**gpt-6-astra**。本轮只处理交付检查边界；不改产品、测试、R461 原件或索引。

**问题与原始证据：** ROOT 的全暂存范围 `git diff --cached --check` 返回 2，外层 exec 返回 1，chunk `42be6e`，commit 尚未执行。工具返回正文原样保存于 `intake/git-staged-check.original.txt`，来源说明见 `intake/failure.json`，没有重跑。R461 已暂存 24 路径。该失败必须继续作为失败保留。

**根因及只读核对：** 原编号摘录把空源码行表示为 `107: `，行号后的分隔空格是原始摘录格式。已核对 339 条编号内容与对应源码逐行一致；保存的 22 条告警全部恰好对应该文本的编号空源码行。`intake/source-check.json` 保存逐项来源；`intake/input-pins.json` 冻结必要来源、清单及失败原件 SHA256。没有产品空白问题的证据，不进行 trim/rstrip 或全局规则关闭。

**限定执行步骤（ROOT）：**

- [ ] 复核本计划与 pins，逐项核对保存的 22 条告警、339 条来源摘录及 R461 暂存 24 路径/字节与原 manifest 一致。禁止改动 R461 manifest。
- [ ] 新建最终显式路径/SHA 清单，只增加 R462 计划、intake 和核对报告；逐路径 stage 新文件，不使用 `git add .`，不触碰历史脏 gitlinks。
- [ ] 样式检查仅排除下面两个确切原始文本，其余最终交付文件全部包含（计划、JSON、specs、代码副本及其他原件）。用结构化 argv 执行一次 `git diff --cached --check -- <显式全部检查路径>`，保存 stdout/stderr/rc；不重跑原全范围命令。
- [ ] 新增的检查结果/清单须另行核对字节与样式后显式 stage；再次核对最终 index 路径/SHA 集，不用额外全套测试代替。任何其他告警或 scoped rc 非 0 即停止，不扩大例外。
- [ ] 上述条件成立时，沿既有交付授权原样提交、推送 `research/20261004-continuation`，核对 local/upstream/remote 三方 SHA；ROOT 保存结果，不由本规划 agent 操作 Git 写入。

**只做完整性核验的两个精确路径：**

1. `artifacts/research/process/20261004-ced-development/astra-rounds/round461-sol-evidence-reader-and-mainline-plan-20261108/intake/static-evidence.txt`
2. `artifacts/research/process/20261004-ced-development/astra-rounds/round462-planning-evidence-delivery-check-20261108/intake/git-staged-check.original.txt`

第二份包含原告警中带空格的原行，必须保留相同字节。不得使用整个 intake 目录或通配后缀作为排除范围。

**验收边界：** 原全范围检查仍 rc2；独立命名的 scoped authored-file 检查 rc0；原证据 SHA/来源核对通过；所有 staged bytes 与显式清单一致。只能报告这三件事，不能称原全范围检查已 PASS。模型 API、测试、physics、render、服务操作全部 0；不改变研发或研究资格。新根因/范围扩大再次交实际 Astra。无需新增框架或重复 R461 的软件/规划审查。
