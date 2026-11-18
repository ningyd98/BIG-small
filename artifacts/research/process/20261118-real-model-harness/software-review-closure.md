# H1、Phase 12 与 UTC 软件复核

基线 `318a546dd3a945bddc076cc06bc3528966a4051a`。H1 并发输出归属已关闭，UTC 门维持通过。Phase 12 来源门仍有 **1 项 Important**，涉及 Astra 计划中已明确要求的 profile 和阻塞原因位置。H1 与 UTC 可独立提交，Phase 12 补充入口待修。研究与物理验收、正在迭代的 native 视觉接线均未纳入本次结论。[前次审查](software-final-review.md) · [本轮实际 Astra 计划](../20261004-ced-development/astra-rounds/round-harness-source-ownership-20261118/plan.json)

| 前次问题 | 当前结论 |
| --- | --- |
| 原七项 1 · 正确原生环境 | 已关闭；同子进程的冻结 R545、解释器/依赖/CPU ABI 与 checkout 绑定保持。 |
| 原七项 2 · 子进程退出与成本 | 已关闭；已启动却缺证据时保留退出/信号和 null 成本。 |
| 原七项 3 · 阻塞试次来源 | 原来的重复 ID、状态和执行标记用例已关闭。来源门其余条件见下文。 |
| 原七项 4 · 计划与准备配置 | 已关闭；固定场景的有效配置单列。 |
| 原七项 5 · 证据缺少阶段 | 已关闭；仅 schema 的结果被拒绝，完整 PREPARED 需绑定场景与来源。 |
| 原七项 6 · 来源取错工作目录 | 已关闭；ROOT 的 commit、实际脚本、adapter 与本次新依赖 registry 哈希已核对。 |
| 原七项 7 · 数字布尔 | 已关闭；值为数字的配置仍被拒绝。 |
| 后两项 1 · H1 并发归属 | 已关闭；保留了先前 RED 和两组四进程 GREEN。 |
| 后两项 2 · P12 误认阻塞来源 | 原三例均已拒绝。计划中明确列出的 profile 及原因子句两部分尚未满足。 |

## H1 证据归属

独立重算新 wheel SHA256 为 `787d6937ea7447c51282a159d4952da2b201dca193746dcbcedc4d2759a72270`，逐项核对 5 个源码或说明文件及 78 个留档文件指纹，wheel 内 Harness Python 文件与当前树一致。打开源码与清洁 wheel 各自四份归档 stdout，均仅 seed 42002 为 PREPARED/0，并且有效 seed 匹配。其余三份均为 NOT_STARTED/2，未引用胜者期次或清单。锁在启动前按规范输出路径独占获取，子进程继承同一描述符，结果核对后才关闭。此次独立运行父进程被杀、归属误配及拒绝路径的 6 项测试，全部通过。完整 86 项为实施轮的已存结果。[归属证据](h1-output-ownership/verification.json) · [轮包并发结果](h1-output-ownership/wheel-green/result.json)

## Phase 12 剩余 Important

所审脚本 SHA256 为 `0ec96d5a912ce69cf411c2dda4cb130284a35bb0c51f523c98a1a42ff36cebee`。取已冻结 `raw_runs.jsonl` 中的 `phase12-00523`，每次仅改表中一项并调用 `read_original_rows(raw, count=1)`。四种输入均返回一条合格旧行。

| 变更 | 当前输出 |
| --- | --- |
| 将 `profile` 从 `validation` 改成 `full` | 接受 |
| 删除 `profile` | 接受 |
| 将 `failure_type` 改成 `main: no RGBD_CAMERA_REQUIRED occurred` | 接受 |
| 将 `failure_type` 改成 `unrelated_stage: RGBD_CAMERA_REQUIRED` | 接受 |

当前代码没有检查 profile；对原因只在任意位置匹配完整词，未校验登记的 main、recovery 或 duplicate 阶段及可选 RuntimeError 前缀。按既有计划补齐 validation profile 和实际错误码位置，使用登记 F20 的 backend、control 和 scenario。将这四个例子作为输出创建前与 adapter 构造前的负例，保留已有来源正例。

本次独立运行现有 20 项来源与身份测试，全部通过。真实 18 条均为 validation，旧 raw SHA256、修后源码身份和摘要中 18 项 ID 顺序均再次匹配；本发现不改变已存 1+18 次的软件生命周期证据。本次未执行新生命周期试次。[18 条来源复核](phase12/strict-source-verification.json)

UTC 的原 381.627 秒联合门和上次独立核对的 AST、来源及运行原件仍适用，本次未重跑长门。[UTC 联合门原件](../20261004-ced-development/astra-rounds/round-utc-codec-performance-20261118/verification/result.json)
