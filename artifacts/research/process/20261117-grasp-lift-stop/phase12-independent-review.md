# Phase12 追加修复与分组证据独立只读复核

审查对象：`41bb33344c0463a979327d0c78e2acd1088b458f..8a6f7a8e9d2584267b8ab7b0e4167e648ec66ad8`；工作树 `/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`。读取本轮 Astra plan.md、Git diff、原分组清单/summary/JUnit、路径前置复测、Phase12 控制及原件重放记录；没有执行测试、模型或真机，没有修改仓库或原始证据。

## 结论

追加修复无代码层面阻断发现。它符合窄修计划，保留真实 F20 阻塞及正负控制。可采用“原分组加限定复测、两个测试树修订、同一生产源码”的去重覆盖说明；不得称 7,101 项在单次运行或同一完整 Git SHA 上全量通过。复核后续收到新 clean 单项完整证据并核验通过，允许闭合为 7,069 PASS + 32 SKIP；UTC 600 秒门禁失败及历史 56 FAIL 仍单独保留。

## 差异及继承成立条件

- `git diff --stat` 仅一个文件：`tests/test_phase12_2_runtime_authenticity.py`，40 insertions / 21 deletions。生产 verifier、adapter、所有其他源码未改。
- AST 忽略行号的函数体比较：既有定义仅 `test_paired_summary_marks_isaac_blocked_as_not_accepted` 改变；新增一个三参数负控制测试；仅移除 `_assert_validation_status_matches_provenance`。旧提交 `git grep` 显示该 helper 只有一个调用，正是被改目标测试。不存在其他测试依赖被删除共享 helper 的情况，其他既有测试函数/fixture/helper 的 AST 均未变。
- 新目标保留 paired/count 断言，显式要求三项运行 evidence=false、GAP、NOT_READY、NOT_RUN。未设置 LEGACY_PIPELINE、未改变 RGBD 入口、未降低生产验收条件。
- 新三例负控制基于既有最小 fixture 和同一 patch helper，每次单独将一项 evidence validator 置 false；要求真实测试 fixture 的 provenance check=true，GAP、NOT_READY、NOT_RUN、gated authoritative count=0。既有正控制仍要求 ACCEPTED/PREREQUISITES_READY/NOT_RUN；dirty provenance 负控制仍要求 GAP 且 gated count=0。controls-final.xml 对应五例 0 failure / 0 error。
- 原分组 source-manifest.json 共 1,063 个文件，逐项与当前字节 SHA256 比较，唯一变化是上述测试文件：`8278bff37a907727fd0da2a8d44588bc4fa4496e4ab6580dc7b4dcedc51e58bf` → `51cbad1dc67249f768e196d3cbf2e3496ccdc04ca587270801066ab816e33727`。

## 源漂移与 UTC 两例

原 summary 保留 `same_source_at_finish=false`，此字段不能改写。当前可观察文件时间为：最后一个非 UTC 分组 suite-03/result.json 在 23:15:31.716820 写出；目标测试最后修改时间 23:16:44.986914；8a6f7a8e 提交时间 23:17:15；UTC memory/sqlite 分别在 23:18:21.742063 / 23:18:23.394316 写出结果。mtime 仅证明最后一次修改的顺序，不独立证明首次编辑时刻；因此应与父任务操作记录共同描述修改期间仅剩 UTC 两例，不能把 mtime 当完整历史审计。

两个 UTC start/result 均明确记录原启动 source_commit=41bb3334；JUnit 各 1 PASS，耗时约 2,466 / 2,468 秒。节点为 `tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[memory|sqlite]`。该文件、conftest 和递归静态 tests 导入依赖闭包（20 文件）不包含 Phase12 测试；源码/脚本内也未找到对该测试模块的引用。检查 UTC helper、工厂和 source_root 构造：工厂按生产源路径集复制所需文件，不读取 Phase12 测试。结合清单仅一个无关文件变化，可保留两例为“41bb3334 启动、相关测试及生产依赖未变的诊断 PASS”。这不是“全树在整个运行期间未变”的声明。

UTC 联合 600 秒门禁单独为 TIMEOUT_UNCOMPLETED=2、returncode=-15、passed=false；诊断 PASS 不能代替这个门禁。故不得宣称所有门禁通过或 all_applicable_checks_green=true。

## 原件与计数核对

- 原分组：7,098 个唯一节点 = 7,010 PASS + 32 SKIP + 56 FAIL。
- 路径前置复测 JUnit 实际 59 PASS（vault=56、offline=3）；与原失败 node id 集合精确相交为 55，另 4 为原已 PASS 节点，不能重复加到覆盖总数。剩余原 FAIL 唯一是本次 Phase12 慢节点。
- Phase12 控制共 5 PASS，其中 2 是已有节点，3 是新增节点；controls/controls-final 两次不能重复累计。
- 原件断言重放共 2 PASS，明确 `runtime_invoked_by_replay=false`；不增加 pytest 节点或新运行次数。
- 最新 collection 为 7,101。若 clean 慢节点完成，则合并唯一节点结果是 `7,010 + 55 + 1 + 3 = 7,069 PASS` 和 `32 SKIP`，总计 7,101；原始 56 FAIL 继续作为历史证据保留。查验时 single.log 尚停留目标运行行、无最终结果，因此当时口径为 7,068 已有 PASS 证据 + 32 SKIP + 1 待新运行确认。
- 两份原件的 replay 记录所列 paired/summary/provenance 哈希与当前字节均一致。两份 summary 都是 GAP/NOT_READY/NOT_RUN，三项运行 checks=false；两份各有 18 条 F20 raw `BLOCKED_BY_ENV`，failure_type 均明确 main/recovery/duplicate 的 RGBD_CAMERA_REQUIRED。

## 精确发现：派生重放记录 commit 字段映射缺失

`phase12-gap-recheck/artifact-replay.json` 两条 `artifact_provenance.git_commit` 都是 null；原件真实字段名为 `source_commit`，不叫 `git_commit`。旧脏原件是 `f258df862d96f25c2a0507f4b3b9f4f83049aa75`，本次原失败净原件是 `41bb33344c0463a979327d0c78e2acd1088b458f`。原件包含正确值且哈希匹配，因此不构成原件缺失或造假；应在新派生覆盖/步骤报告明确补充正确 source_commit 映射及执行测试代码 SHA，并保留原 replay 文件，避免靠 null 字段声称完成 SHA 记账。

正式研究边界继续是 F20 未调用执行器/运行证据缺口、full profile NOT_RUN；软件测试通过不能升级为模型/真机或论文正式验收，也不构成完整远端复现包。

## 补充：新 clean 单项已完成并独立核验

已读取 single-command.json、single-proof.json、single.xml，并对照实际 raw 中的 summary/provenance 与日志/JUnit SHA。命令返回 0；JUnit 1 PASS，418.065 秒。原始 provenance 明确 source_commit=8a6f7a8e9d2584267b8ab7b0e4167e648ec66ad8、worktree_clean=true，测试文件 SHA 匹配，命令记录 unchanged_test_file=true。实际 raw 仍有 18 条 F20 BLOCKED_BY_ENV 且全部包含 RGBD_CAMERA_REQUIRED；summary 仍为 GAP/NOT_READY/NOT_RUN，三项运行 checks=false，provenance check=true。该补充关闭上文初查时的一项待确认；最终唯一节点计数 7,069 PASS + 32 SKIP = 7,101 可以使用，但不能覆盖 UTC 600 秒门禁，也不能称 8a6f7a8e 单次整库执行。
