# R149：ROOT new19 冻结索引的 null source 读取恢复

实际规划者 gpt-6-astra，2026-10-12。冻结待 ROOT 激活。完整输入绝对路径、bytes、SHA256 与执行合同见同目录 plan.json。

原工具 b52658 实际 exit 1：读取器将每条 files.source 都交给 Path，遇到 null 报 TypeError。原命令、完整工具返回和 combined output 均保留；独立 stdout/stderr 不可得，不重构。失败发生在输出/账本/STATE/PHASE 写入之前。原 new19 已实际 exit0、19PASS、spent1/0，本问题不构成产品失败。

独立读取真实索引确认：1208 条 files 包含 6 source、5 raw、1192 fixture、4 ledger snapshot、1 author_report。仅 author_report.source 为 null，其 snapshot 是已生成的 step-report.json（213300B，SHA256 6adcb82b39f595e26e2eaae50ab4f364bf7bc56a96a3f6088a992596823b6bcb）；没有独立来源文件是合理格式，snapshot 的核验仍不可省略。另 53 protected 和9 references 使用 path；7 symlink 使用路径及 lstat/readlink 字段；18 lifecycle 使用 source/snapshot。不会将这些不同集合套用同一错误字段假设。

限定 ROOT 新建一个 stdlib 元数据 reader，完整文本审阅后单次执行；不重放旧 heredoc。新脚本：
/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round149-p6-root-new19-index-null-recovery-20261012/implementation/read-new19-index.py

命令为 .venv/bin/python 加该绝对路径，cwd /home/ningyd/文档/ChatGPT/BIGsmall。新增产品额度为零。原 pytest、static、positive、foreign 与所有 spent 命令均不重跑；不修改源、测试、原 runner 或冻结记录。

读取器必须：
- 按真实 schema 核对全部1208 snapshots 和1207存在的 source，仅对唯一精确 author_report 记 source_not_applicable，不能跳过其 snapshot hash。新 null/异常字段 fail closed。
- 按集合实际字段检查53 protected、9 references；7 symlink 仅 lstat/readlink，不追随。数据库仅字节哈希，不打开 SQL，不复制整树。
- 核对原 new19 的 exact argv/cwd/env、actual result、独立 raw、JUnit 精确19节点及无 failure/error/skip；四份 JUnit 从 index.runs 的已知 pins 获取。
- 保留旧19PASS1FAIL，明确40 unique来源为旧19 retained＋修正foreign1＋new19＋CPUpositive1；核对旧 source proof/受限 delta，绝不称单次40运行。
- 仅读18真实 lifecycle 的已验 snapshot 并保留 source provenance，核 session_closed/raw_exit1/shutdown1，不补造缺失记录。
- 独立 exclusive-create JSON 结果；stdout 只打印绝对路径、bytes、完整SHA与少量计数，少于1500字符。保存本次真实分离输出与数字exit，step记录实际工具返回；不解析带前缀/截断的 transport 为JSON。

只有全部核对成功才允许正常元数据同步：先保存两ROOT账本、STATE和PHASE before件，再防并发比较当前字节；只将 R127 root commands.new_green 与 R147 root inherited_new_green19 的派生耗用同步为 actual1/0 exit0并记录来源。旧冻结 ROOT pending0/1是明确的捕获时序，不是新额度，也不得反写旧快照。STATE仅更新本次事实、40unique映射、剩余额度及 fresh-review-pending；PHASE只追加。保存限定字段diff和前后hash，不动其他任务、授权、失败、Git或验收值。

ROOT 可在本轮新建 input-check、activation、script-review、执行capture/result/reader、before件、sync-report及step-report；精确路径和允许现有元数据字段见JSON。任何检查不匹配不得同步状态或重试，保留可得原件并停交实际 Astra。

本轮只解决元数据读取和事实同步。独立终审继续且尚待；40unique软件证据并不自动验收A。Stage A仍为 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO；不激活B/C/D，不声称native、physics、actual或formal通过。

