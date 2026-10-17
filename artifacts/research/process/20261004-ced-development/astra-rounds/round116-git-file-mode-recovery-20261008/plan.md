# R116 — Git 文件模式元数据恢复

实际 Astra（gpt-6-astra）；仅本地计划，不加入 R115 的23路径交付。

ROOT 工具 ac9d3c 在候选验证时退出1（stdin第34行 AssertionError）：错误要求 POSIX 权限恰为0644。三个既有文档实际0664，仍属于 Git regular non-executable 100644。d25d48 已定位；原输出与步骤报告保留，本轮不重构原命令。原前置、activation、20文件copy及3doc编辑已完成；stage/check/commit/push尚未执行。

本次只读复核23项（20manifest entries加3activation self pins）全部SHA/bytes一致，均regular且无execute bits；结果及6输入SHA在plan.json。此处没有产品执行或Git mutation。

ROOT 最小恢复：

1. 保留已准备候选和原activation。复核23项 expected字节，改用lstat、S_ISREG和无任何0111执行位；不得chmod或要求0664变0644。symlink/非regular/execute位仍拒绝。
2. 只补尚未完成的candidate-manifest及本地恢复收据；不从clean前置重启，不再copy/append，不覆盖原失败或R115计划。
3. 继续原23路径暂存。通过 `git ls-files --stage -z -- <exact23paths>` 核对每项stage0/mode100644，并保留原staged blob哈希/大小/全集校验。
4. 沿用R115未用whole/strict各1及commit/push各1；真实exit、原样异常逐行登记、strict0/unclassified0、正常nonforcepush、三SHA/clean与祖先隔离均不变。R116仅由本地postpush报告引用，不新增发布路径。

不改变文档权限/内容、产品、测试、P6激活或预算。软件/actual/formal新增均0。本轮完成只表示元数据恢复计划冻结；推送由ROOT继续执行。
