# H0/H1、Phase 12 软件生命周期与 UTC 最终独立审查

审查基线为 `318a546dd3a945bddc076cc06bc3528966a4051a`，验证对象为该基线上当前工作树的限定文件。**本次有 2 项 Important，0 项 Critical，0 项 Minor。** 建议先修正 H1 的并发证据归属与 Phase 12 来源预检，再接受这两个入口。UTC 软件门可单独接受。原生视觉接线、GPU、模型运行与物理效果均在本次审查范围之外。

## Important

1. **并发使用同一新输出目录时，失败调用会把胜者的期次报告为自己的 PREPARED。** 在源码树外、去除凭据和 Python 路径变量的环境中，使用已验 SHA 的 clean wheel，将四份仅 seed 不同的配置并发传给同一 `prepare --source-checkout ... --output ...`。原调用结果如下。源码入口独立重复时由 55103 胜出，也出现相同行为。每次均只创建一个真实期次，问题出在结果归属。

   | 计划 seed | 子进程/CLI 退出码 | 返回状态 | 所引用的有效 seed |
   | --- | --- | --- | --- |
   | 55101 | 2 | PREPARED | 55104 |
   | 55102 | 2 | PREPARED | 55104 |
   | 55103 | 2 | PREPARED | 55104 |
   | 55104 | 0 | PREPARED | 55104 |

   `harness/cli.py:227` 的存在性预查与原子建目录之间有时间窗口。失败子进程的原入口收到 FileExistsError 后退出 2。到 `cli.py:166` 输出路径已经存在，封装跳过了子进程的未启动回执，随后在 `cli.py:193` 读取胜者的清单。最小修复是让“无法独占创建期次目录”的结果可以由本次子进程无歧义地识别，并在读取任何该目录的证据前返回未启动。可在 mkdir 处使用专门的冲突回执，避免把归档阶段也可能产生的 FileExistsError 一概当成启动前失败。回归应强制两个调用都到达同一个建目录窗口，验证只有胜者返回 PREPARED，失败调用不引用对方的清单、阶段或计数。既有“本期次已启动、清单缺失”的信号和成本语义需同时保留。

2. **Phase 12 补充入口仍可把不合格旧行当作已证明的 F20 摄像头阻塞。** 对实际旧 `phase12-00523` 单行各作一处变更，将原始字节传给 `read_original_rows(..., count=1)`。以下三例均被选中，返回一行。按 `scripts/run_phase12_runtime_lifecycle.py:96` 的正常调用顺序，随后即可创建输出及 adapter。本次只运行预检函数。

   | 单项变更 | 预检漏过的条件 |
   | --- | --- |
   | `scenario_id="NO_SUCH_SCENARIO"` | 第 68 行仅要求非空字符串。项目 F20 注册项只包含 `S15_SQLITE_RESTART_DURING_RUN`。 |
   | `failure_type="main: NOT_RGBD_CAMERA_REQUIRED"` | 第 62 行子串匹配把其他错误码认作原 RGB-D 阻塞。 |
   | 同一原始 JSON 对象依次写入 `"runtime_invoked": true` 和 `"runtime_invoked": false` | 第 42 行的默认 JSON 解析丢弃前值，后续检查无法辨认冲突原件。 |

   最小修复是在现有输出前预检中使用拒绝重复键的 JSON 读取方式，按 F20 的登记场景检查 linked 行，按已登记的阻塞原因码及其分隔边界识别原因。standalone 初测可继续使用独立场景。以三份原始字节回归，在 adapter 构造和输出创建之前拒绝，同时保留原 18 行的逐项映射正例。原有 synthetic linked 正例使用 S01，若采用登记场景检查，应改用真实 F20 的 S15。

## 前次七项

| 前次审查项 | 复核结果 |
| --- | --- |
| 1 原生准入 | 原失败已关闭。同一子进程运行冻结的 R545，先检查解释器、baseline.pth、依赖实际路径/版本/哈希和 CPU ABI，再检查 checkout 中已加载项目模块并委派原入口。正确解释器 CPU help 退出 0，错误解释器退出 2，未创建期次。 |
| 2 已启动无清单 | 原来的退出 7 和 SIGTERM 两项已关闭，仍分别保留退出值 7/−15、信号、封装退出值及 null 成本。并发输出归属尚未关闭，见本次第 1 项。 |
| 3 旧行预检 | 重复 ID、原 SUCCESS、缺状态、非 false 执行字段等既有用例已关闭。对 malformed 原始行、场景和阻塞原因的覆盖仍不完整，见本次第 2 项。 |
| 4 准备配置 | 原失败已关闭。单次开发 seed 的 planned 配置和哈希独立列出，effective 从原固定场景 assignment 取得，差异列出 scene_split、servo、camera。 |
| 5 证据阶段 | 原失败已关闭。schema-only、缺状态及缺绑定文件的完整 PREPARED 被拒绝，既有 FAILED/INTERRUPTED 仍可索引。 |
| 6 来源身份 | 原失败已关闭。脚本使用自身 ROOT 计算 HEAD，记录实际脚本与已导入 adapter 的源码哈希。旧摘要未重写，复核证明使用修复后的身份。 |
| 7 数字布尔 | 原失败已关闭。配置在 Literal 检查前要求值为严格 true，拒绝数字 1 与 1.0。 |

## 验证边界与证据

- **H0/H1。** 独立重算 wheel SHA256 `aee16cc067fa57db2871e9bf6652608703054f8d3b0e410eec895ecac1ccd7e9`，核对 9 项源码/说明、29 项已存验证工件，以及 wheel 内各 Harness Python 文件、示例 JSON 和共享资源准入代码。clean 日志具备源码树外 help/version、validate、doctor、prepare、evidence 与双解释器 CPU help 的实际退出。默认入口无付费调用或硬件派发，旧 probe 别名和原 episode 均指向共享资源检查。此次另跑 Harness 29 项，4.93 秒全部通过。既存 79 项含上述 29 项及 50 项原 CLI 回归。[H1 证据](h0-h1-review-fixes/verification.json)
- **Phase 12。** 当前来源与 cwd 回归 16 项通过。根据原始 raw SHA256 `1bc6f6975cef1a23e58e6805ce725b1b96ed1cdebdaceebfa4ba248a6300419a` 重新筛出并核对 18 项 ID 和顺序。对既存初测 1 条和补充 18 条逐一重算回执文件和 SQLite 哈希，检查内部哈希、恢复、竞争、终态 artifact 判据与软件范围，结果全部匹配。默认 adapter 继续选择 RGBD，登记初版回归验证零 executor，主 runner 和 validator 无 diff。本次没有运行新 lifecycle。旧来源和 18 条真实补充的既有关系仍成立。[Phase 12 初始验证](phase12/verification.json) · [修复后来源指纹](phase12/review-fix-verification.json)
- **UTC。** 对原两节点测试函数重新做 AST 比对，去掉观察器的一个选择参数后与基线完全一致。代码保留外部 strict snapshot、嵌套验证、R315 成功项完整字节及类型键、128 项/8 MiB 限制、context/token 所有权和根退出清理。新导出每次从已验证 JSON 重新解析，可变输出互相独立。重新核对联合运行前后源码、JUnit、日志、资源原件、7 个邻域日志/JUnit 对和 11 个验证工件指纹。历史联合执行一次，两节点同进程通过，外层计时 381.627 秒，上限 600 秒。48 项 codec/安全回归通过，4 组观察器 A/B 记录相同 codec 摘要和正常清理。本次未重跑长 UTC 门。[联合运行原回执](../20261004-ced-development/astra-rounds/round-utc-codec-performance-20261118/verification/result.json) · [UTC 验证汇总](../20261004-ced-development/astra-rounds/round-utc-codec-performance-20261118/verification/summary.json)

以上仅为软件开发与既有本地原件审查，正式研究和物理验收仍按原边界记录。
