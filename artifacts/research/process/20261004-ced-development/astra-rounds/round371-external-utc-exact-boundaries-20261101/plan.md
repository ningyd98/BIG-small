# R371：外部 UTC 精确边界修复计划

实际规划模型 **gpt-6-astra**，agent `/root/astra_r371_utc_plan`，2026-11-01。此阶段只规划；用户“现修复1,UTC的问题”已授权后续限定修复，不需要再索要确认或交回文档。完整输入 bytes/SHA256、回归矩阵和命令字段见同目录 `plan.json`。

## 问题与证据

R370 真实短 GREEN 为 **1 failure / 0 error / 0 skip，exit 1，无超时，源前后相同**；字段构造问题已越过，失败为 helper 第 5614 行 `assert (None is None) is False`。原件位于 `../round370-p6-t3-request-id-closure-20261026/implementation/external_utc_green_01/`，不得覆写。原 JUnit 未显示 offset，不能把推断说成原日志直接记录。

同函数两分支都用 `int(delta.total_seconds()*1000)` 决定新鲜度。仅 stdlib 标量核算得到：精确 age −1001000μs 经浮点乘法为 −1000.9999999999999ms，`int` 得 −1000；精确 age 5000001μs 则被截成 5000ms。前者结合原循环顺序强烈定位 +1001ms 的失败，后者证实同根因可吞掉 TTL 外的微秒。因此两分支可合并一轮，不需要独立产品诊断执行。

## 最小修改

1. 先在原短合同文件 **追加** 两个具名循环回归，保留原 4006 字节内容及全部断言。模型必须真实校验，只有 pipeline 时钟固定。观察分支复用真实 RGBD；summary 分支构造确实充分的对象、Pose 和区域。每行断言打印 branch、offset_us、TTL。
2. 仅修改 `pipeline.py::check_scene_sufficiency`：用精确 `timedelta` 比较。有 observation 时无效条件为 `age < -timedelta(seconds=1) or age > timedelta(milliseconds=scene_staleness_ms)`；无 observation 时仅 `age > timedelta(milliseconds=scene_staleness_ms)`。边界等号仍有效；保留默认 5 秒 TTL、观察分支未来容忍 1 秒、summary 不检查未来时间的既有语义。原整数毫秒可仅用于错误文案，不能再参与判定。深度与其他场景校验顺序不变，不新增时间工具或改模型。
3. 原 helper 保持当前字节，包含 R369 的 `updated_at=external.captured_at` 与 R370 的 `request_id="external-utc-contract"`。不改断言、阈值或完整 UTC 测试。

默认 TTL 下两分支各检查 offset_us `[999999,1000000,1000001,1001000,-4999999,-5000000,-5000001,-5001000]`。观察分支有效性 `[T,T,F,F,T,T,F,F]`；summary `[T,T,T,T,T,T,F,F]`。两分支另检查 TTL=1001ms 的 `[-1000999,-1001000,-1001001,-1002000]`，应为 `[T,T,F,F]`。加上保留的原四毫秒边界、expired decision 和输入不变断言，覆盖浮点与微秒截断且不改原语义。

## 执行身份、额度与验收

**复用 R370 真实失败作为 RED；新增同根因回归不要求独立 RED。** R370 槽仍 SPENT。新身份 `R371:external_utc_green_01`，仅一次串行 GREEN，child **30 秒**、outer **60 秒**、outer kill-after 20 秒，cleanup 总 15 秒含 TERM 5 秒，capture 10 秒；重试、额外 RED、自检、长 UTC、worker/DB/model/physics 均为零。

复用 R370 有限 runner，只改轮号、路径、plan pin、单命令元数据及过时 docstring；五节点由 plan.command 映射，核心 source/env/capture/cleanup/judge 不变。新目录和单槽 ledger；静态对比即可，不重跑七项自检或宣称新版已重新认证。执行前复核输入 SHA、限定 diff、环境和独占写入条件。后续 root 执行，不由规划者运行。

一次命令包含原合同、新增两节点、既有 `test_stale_scene_triggers_sufficiency_check` 和 `test_stale_rgbd_blocks_before_model_call`。后者静态确认在 stale gate 返回后才可能调用模型；只选该 node，不运行同文件 HTTP 测试或整文件。

子命令：

```sh
'/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' -m pytest -q -p no:cacheprovider tests/test_operational_external_utc_scene_contract.py::test_external_utc_scene_contract tests/test_operational_external_utc_scene_contract.py::test_rgbd_scene_exact_utc_boundaries tests/test_operational_external_utc_scene_contract.py::test_summary_scene_exact_utc_boundaries tests/test_phase4_cloud_planning.py::test_stale_scene_triggers_sufficiency_check tests/test_rgbd_planning.py::test_stale_rgbd_blocks_before_model_call '--basetemp=/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round371-external-utc-exact-boundaries-20261101/implementation/external_utc_green_01/persistent-basetemp' '--junitxml=/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round371-external-utc-exact-boundaries-20261101/implementation/external_utc_green_01/junit.xml'
```

外层命令（cwd 为项目根目录；须先按计划准备 runner 和 ledger）：

```sh
/usr/bin/env -i 'PATH=/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin:/usr/bin:/bin' LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src:.:tests /usr/bin/timeout --signal=TERM --kill-after=20s 60s '/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round371-external-utc-exact-boundaries-20261101/implementation/run-r371.py' external_utc_green_01
```

验收为 **精确五节点、5 passed / 0 failure / 0 error / 0 skip、exit 0**，无超时/截断/证据缺失，执行期间 source-before==source-after，全部边界与原合同断言实际完成。保留原 streams/JUnit/invocation/result/cleanup/source 及 runner 身份；写一份 phase-step-report 并汇入阶段总结。失败/范围扩大/新根因须保留证据交下一轮实际 Astra，不自动重试。只验收开发层 UTC 场景新鲜度；完整 UTC、性能、真实运行和正式研究仍未验收，600 秒原标准不变。

## Git 交付

验证通过后按根 AGENTS **显式路径提交并推送**当前 `research/20261004-continuation`，上游 `origin/research/20261004-continuation`；提交本轮 product、原 helper 两处构造修复、短合同及新增回归，附精选小型原失败/计划/结果/步骤证据。推送后核对本地、上游与远端 commit SHA。不可 `git add -A`、重写历史或混入未提交 `local_temporal.py` 性能修改、copy/sha 测试、嵌套工作区和其他报告。环境证据入远端前排除凭据，必要时仅添加明确标识的脱敏派生件，保留原件与 hash；清单不能冒充完整复现包。

输入清单不递归继承所有旧轮次；本计划只锁定本轮直接依据、选定回归及需要保持的脏文件。真正未确定项仅是修改后五节点的实际运行结果和完整 UTC/真实运行尚未执行；不额外增设用户交回文档或多层门禁。
