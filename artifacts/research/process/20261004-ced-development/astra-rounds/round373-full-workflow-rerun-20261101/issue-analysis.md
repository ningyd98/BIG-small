# R373–R375 问题分析与验收边界

本页说明已完成诊断所支持的结论。完整终态数量以阶段总结和 R374 最终覆盖清单为准；原始失败、超时及后续对照分别保留。此处的后续方向是问题分解，不是已经实施或批准的新修复计划。

## 1. UTC 功能边界已验证，原运行时限未达标

R371 的 5 项短回归在本轮均有新的通过事件。覆盖外部 UTC 场景合同、RGB-D 和摘要精确边界，以及两个既有过期输入拒绝用例。memory/SQLite 两组完整 UTC 长场景也分别通过，包含启动前偏移一天、回拨一天及硬截止后的回复不得发布。

两组外层实耗分别为 2356.436263571 秒和 2354.929862193 秒，合计 4711.366125764 秒，约 78 分 31 秒。原两后端合计 600 秒的验收没有满足。扩大诊断上限只让断言有机会执行完毕，不会改变原验收标准。

该运行使用含未提交 `local_temporal.py` 性能候选的脏工作区，没有干净 HEAD 或受控 A/B 对照，不能据此宣布性能改善或确定耗时归因。偏移在每个新场景开始前安装，未演示同一活动任务中真实宿主系统时钟突然跳变。资源清理证据已记录，但未观测的 OS/GPU/网络/native 外部量仍为 null。

后续应先用新 Astra 计划定位计算与等待的时间分布，再以相同源码、输入、环境和原合计时限复验；不能仅继续加大超时。参见 [UTC 范围说明](../round374-diagnostic-runtime-prerequisites-20261101/reporting/utc-coverage-boundary.json)、[memory](../round374-diagnostic-runtime-prerequisites-20261101/reporting/utc-memory-result.json) 和 [SQLite](../round374-diagnostic-runtime-prerequisites-20261101/reporting/utc-sqlite-result.json)。

## 2. T3 四项公共结果读取失败：测试输入合同不完整

confirm_timeout、prior_bound，以及 memory/SQLite 正常发布对照共四项，在 `SimulationRuntimeService._run_record` 验证 `ExperimentManifest` 时失败。持久记录中的 `manifest_json` 为 `{}`，缺少六个必填字段。继承的测试工厂最终直接创建 job，未传入正常服务入口会提供的完整 manifest。

有些拒绝场景已留下拒绝记录，两个正常发布对照也留下 CONFIRMED 和结果文件，但公共结果读取未成功完成，四项整体验证仍是失败。不能把局部记录当成完整通过，也不能为了测试通过而放宽生产读取合同。

后续最小修复方向是核对测试工厂与正常创建入口的合同，保留真实公共读取断言，并复验相关正常与拒绝场景。是否需要调整产品必须由证据另行支持。参见 [源合同审计](../round374-diagnostic-runtime-prerequisites-20261101/reporting/manifest-contract-readonly-audit.json) 与 [T3 九项结果](../round374-diagnostic-runtime-prerequisites-20261101/reporting/t3-results.json)。

## 3. T3 commit_close 提前终止：尚未进入目标故障点

该用例失败于 `fault["fired"] is True`，实际为 false。只读审计显示 job/attempt 为 INTERRUPTED，操作为终态，原 worker 的结束原因仅保留 `operational_epoch_ended` / `original worker poll ended`；没有恢复更早的具体异常。

因此既没有证明连接关闭故障场景已被执行，也不能由此认定存在不安全发布。下一轮需要先保留并定位提前终止的原始异常与阶段位置，再决定修复测试注入链还是产品路径。不能直接将 fault 标志置真或绕过注入断言。参见 [只读审计](../round374-diagnostic-runtime-prerequisites-20261101/reporting/terminal-commit-close-readonly-audit.json)。

## 4. 两类登记不一致：源码绑定与资产绑定分别处理

标记关联 36 项、范围集成 8 项均在来源绑定检查处被拒绝。登记文件绑定 10 月 5 日的 `marker_association.py` SHA `f538c6b7…`，当前文件是 10 月 17 日版本，SHA `3fb8c536…`。现有证据支持“登记和源码版本不一致”，不支持将全部 44 项解释为算法计算错误。保守拒绝也不能说明当前登记已可用于新运行。

另有资产注册表 1 项失败：`franka_panda_mujoco_scene` 的 `scene.xml` 实际 SHA `66a0e270…`，清单为 `6a793870…`。场景与清单均和 UTC 修复前的提交相同，因此该不一致在本次 UTC 修改前已存在。它与标记来源绑定是独立问题。

后续分别核对各自权威版本、变更目的和需要重新生成的登记证据；不得覆盖历史冻结记录、修改旧实验字节或只替换 hash 使检查变绿。参见 [标记历史审计](../round374-diagnostic-runtime-prerequisites-20261101/marker-source-history-readonly.json) 和 [资产审计](../round374-diagnostic-runtime-prerequisites-20261101/reporting/asset-manifest-readonly-audit.json)。

## 5. 运行未完成：须区分等待、重型流水线与额度截断

原批次及分组续跑有多个超时/未完成节点。分组后续节点尚未执行，不能视作通过，也不能为每个未启动节点虚构失败原因。原批次超时、R374 剩余额度、以及每个实际子阶段的有效上限均单独记录。

闭环心跳用例的只读进程快照在约 289 秒时仅累计约 4.35 秒 CPU，线程处于 futex 等待，未发现计算子进程；这支持继续调查等待路径，但没有 Python 栈证据，尚不足以证明死锁。相关 publication guard 为可重入锁，不能仅凭锁名断言非重入死锁。另有 Phase12 测试会调用完整 validation 流水线，其耗时来源需要单独分析。

第六普通分组末尾的 `visual_full_effect_requirements` 实际仅获约 1.045 秒余量，约 1.529 秒即按额度终止。这是预算截断证据，不是该模块独立运行超过合理时限的证据。分组数据库环境可能影响测试间状态；除已执行的限定对照外，不宣称全部环境/顺序因素已被排除。

下一轮应先选择少量代表节点，固定环境并捕获可解释的等待/进度证据，再决定修复范围和恢复覆盖的运行计划；本轮不自动重试全部失败。

## 6. 两个运行环境问题须与产品修复分开

原 writer-binding 九项失败包含 finally 阶段缺少 `BIGSMALL_R223_RESOURCE_ROOT`；案例目录也是必要前置。R374 为资源和案例提供独立目录后，同一完整模块一次对照九项通过。旧九项失败仍保留，因为 finally 错误可能掩盖更早的异常，不能宣称已排除所有其他因素。

工作台模块的原结果为六项通过、一项失败，WebSocket 首个事件预期 `run_state`、实际 `job_created`。R374 的模块级 `SIMULATION_RUNTIME_DB` 优先于测试各自的临时路径，存在跨用例共享数据库的直接来源证据。R375 只允许在前一批完整终态、进程清理完成后，按原顺序执行七个节点一次，唯一语义变化是移除该数据库环境覆盖；最终结果由 R375 步骤报告记录。

R375 已在上一批终态后执行唯一对照，七项通过、原断言执行、源码不变、六个实际生成数据库的每测试路径证据、内层验收及外层无超时/无残留均已满足。原失败保持。这支持本次修正数据库作用域后的同序对照消除了观察到的失败，不能推广为所有顺序均等价，见[R375步骤报告](../round375-diagnostic-database-scope-20261101/phase-step-report.md)。

## 7. 静态与文档问题独立计数，真实研究前置仍不足

Ruff 1137 项涉及 39 文件；mypy 539 项涉及 18 文件；Python 格式 135 文件、中文说明检查 631 文件、前端 Prettier 11 文件未通过。另有四项中文检查 pytest 失败，包括公开说明缺失以及默认审计收集遗漏。上述静态数量不叠加到 pytest 功能失败数。

按文件字节对比，Ruff 941 项所在文件与 HEAD 相同，189 项位于未提交性能候选，7 项位于未跟踪测试；mypy 对应 524/15。此为文件来源分类，没有干净 HEAD 复跑，不能单凭文件相同推导每项问题的因果来源。

文档检查的 18 次命中包含 11 次脚本引用（五个不同目标）、一处 Markdown 链接、六次敏感文本扫描。扫描命中需语义复核，不等于六次凭据泄露。原始扫描本地保留，派生报告脱敏。

selection/foundation 为未请求执行；power 缺少前置，未运行完整方法先导，assigned denominator 为 null。INITIAL 因缺独立编制的完整资源预算拒绝冻结。真实 Max、独立标定/误差界、合格 B0、风险/方法/功效与 FINAL 等缺口保持，不以软件测试或浏览器 BLOCKED fixture 替代真实研究。JOINT、LOCAL_RECOVER 和真实 dispatch 不因此启用。参见 [静态分类](../round374-diagnostic-runtime-prerequisites-20261101/reporting/static-findings.json) 与 [交付边界](delivery/BOUNDARY.md)。

## 8. 浏览器 Mock 草稿仍依赖旧默认输入合同

默认浏览器套件40项最终21通过、18未通过、1跳过；JUnit把18项分成5个failure和13个error。研究页面另3项通过，不与Python分母混计。默认套件的MuJoCo浏览器用例因没有启用`PLAYWRIGHT_MUJOCO_RUNTIME=1`而跳过；Python关键MuJoCo组的24项通过是另一份证据。

控制台E2E的`draft()`选择MOCK，却省略`input_mode`；当前`ExperimentDraft`默认RGBD。服务在校验时要求RGBD具有真实模拟器相机，Mock仅允许LEGACY_PIPELINE，因此在入队前持久化BLOCKED_BY_ENV。13份捕获的末次API响应均实际包含MOCK、RGBD、BLOCKED_BY_ENV及该阻塞文本；S14还被仅支持S01的RGBD场景条件阻塞。另两项有BLOCKED观测，三项批量测试的成功数为0、预期3，并使用相同草稿。

这是旧测试输入与当前合同不一致的来源证据。没有修改产品默认值、放宽相机要求或重跑测试，不能宣称页面逻辑已被证明有18个独立缺陷，也不能保证纠正草稿后没有其他后续问题。下一轮应先由Astra规划测试合同修正与必要回归，保留当前失败原件。参见[浏览器完整结果](../round374-diagnostic-runtime-prerequisites-20261101/reporting/browser-results.json)、[源码审计](../round374-diagnostic-runtime-prerequisites-20261101/reporting/browser-draft-contract-readonly-audit.json)和[13份响应审计](../round374-diagnostic-runtime-prerequisites-20261101/reporting/browser-payload-readonly-audit.json)。
