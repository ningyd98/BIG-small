# R118：并行提交后状态报告的限定 Git 交付恢复

规划者：实际 gpt-6-astra，经 ROOT 明确委派。日期：2026-10-11。只恢复文档交付，不授权产品开发、测试或真实运行。

## 原始失败与只读归因

ROOT 工具2156ad在任何复制/暂存前第7行固定 HEAD 断言失败，exit1、stdout为空。完整确切stderr保存在 `original-failure.json`；它是会话原始输出的来源明确副本，不是补造完整stdin。

实际只读核对：交付树干净，HEAD/上游为 `3d88fa08a3331fbc8515e7a07315c9d836391882`，直接父为原 `c053db9cd101bcc6a7d5ebb43880f9ff1cc55635`。新增提交仅增加 `docs/开题报告_集成电路工程_20261024.md`，与R117十二交付文件及十六输入路径无交集。16原输入SHA/bytes全部保持；12目标在交付树仍不存在。ROOT此前工具dc725a核实实时远端也为3d88；实施者必须在复制/提交前重核远端。

根因：并行文档提交推进了分支，旧快照HEAD保护正确停止；没有发现内容冲突或产品失败。不能回退并行提交，也不改R117的“编制前c053”历史快照。

## 实施步骤

R1. Before any copy, ROOT rechecks HEAD/upstream/live remote all exactly3d88fa08; direct parent c053; clean worktree/index, same one-file change, zero target overlap, all16 original input pins and all12 frozen R117 file hashes. Require all targets absent; no replacement.

R2. Create R118 validation.json, step-report.md/json and delivery-paths.txt. Explain c053 in R117 is before-authoring snapshot; leave all12 R117 bytes and receipts unchanged. Exact delivery list includes those12 plus completed R118 small files; postpush receipt excluded from commit until it exists and normally kept local-only.

R3. Copy only listed byte-identical files from primary into existing clean delivery tree, without checkout/reset/rebase. Check copies equal pins; inspect exact diff/whitespace and secret patterns in only new public documents. No product tests.

R4. Immediately before staging/commit recheck HEAD still3d88fa08 and remote unchanged; verify only intended new files and empty preexisting index. Stage exact pathspec list, inspect cached path set and bytes. Normal commit parent must be3d88fa08; record actual message/hash. Non-force push existing codex/research-20261007-p1-delivery only.

R5. Verify HEAD/upstream/live remote equal new commit and delivery tree clean; preserve parallel opening-report file as unchanged ancestor. Save postpush-receipt.json locally without changing R117 receipts. Recheck primary original tracked diff and index remain preserved against R117 pre-delivery receipt.

## 限定写入、验证和停点

R117的12文件固定为下表原字节，全部收据不改。本轮仅新增plan.md/json、original-failure.json、validation.json、step-report.md/json、delivery-paths.txt、postpush-receipt.json。后置推送收据通常local-only，以免Git SHA自引用。验证新JSON、精确文件范围/哈希/链接及空白、输入适用性、父提交和推送后三SHA。无产品测试/仿真/付费模型/安装/凭据读取；不重跑R117产品验证（其本来为0）。

若HEAD再次变化、输入/字节漂移、目标冲突、工作树/索引出现无关内容或非force推送失败，立即停相关交付，保留原输出并另交Astra；不checkout/reset/rebase/force、不干预并行任务。ROOT在当前既有授权下沿原隔离交付分支正常提交推送，无需追加用户批准。

验收仅是状态报告和本轮恢复证据的限定Git交付；P6、native、T12和正式研究状态不晋升。完整raw/DB/凭据/权重/SDK不在远端复现交付内。

## 不可变R117输入及SHA256

| 路径 | SHA256 | 字节 |
|---|---|---:|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/delivery-paths.txt` | `1526024351571190b810f3e869de4d03c54bd6e6933b301c9da38d42140dff8e` | 1438 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/original-state/active-t12-state.json` | `f48ff0570a16edf964126d4c4cad087ec591735f21ffa06b3f8e6d48fa0c8726` | 39090 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/original-state/root-activation.json` | `f0bbb9909c76d4afa40c021054c003bbc43d4aff4ba3c2c9786a3d5d42a2f517` | 32879 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/original-state/source-index.json` | `0d5b72b46cd182285b0443d5219ef969ad166ac6664539164cf2746b11aacf42` | 747 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/original-status-observation.json` | `40cd491ccbd90e8cead298b46f8d12fc3d9976eb214522fd1bb2318c7cb967e3` | 16234 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/plan.json` | `4f1cb23a08b1ef29d5eda45ce07bee866f5b16c6771c8962ece7f4889a8544ec` | 15396 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/plan.md` | `148cb8b1fc501169398420efba542172e06cca2cffde8dc4da66cee6e8a0f7cb` | 10359 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/pre-delivery-receipt.json` | `71005a0d464b06c6192c6adddf734b74be7b8495619c559ba3816d81ac2723d9` | 17172 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/step-report.json` | `e1cc8f27e4b2cf66f836daaee143c9dfece27a8fc57dc8be98396e266812c580` | 1023 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/step-report.md` | `c5c4b10f7ac8a8c24270bc8352f721d8ad21d4875639820c9ef49ec0aa21e5f0` | 2327 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round117-project-status-plan-20261011/validation.json` | `7d442fcfc0fd0a2bed6896a329ae2dc4ae25c2a302adba419dcca602256d1d18` | 9249 |
| `docs/research/project-status-and-next-plan-20261011.md` | `9285c8ff0b3ba8aa136620b6b60eedd8740fbc617817716a59e3b6c9e07e27c8` | 13498 |

原16来源的工作区、SHA/bytes与复核结果完整记录在plan.json和original-failure.json；不得仅凭路径混用主树与交付树。
