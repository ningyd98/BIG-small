# R419–R421 fresh Astra 联合审查

结论：未发现需要在本次 P0 选择性研发分支交付前修复的 P0/P1/P2 缺陷。允许按既定边界选择性提交、正常推送，并由实施者另行核对本地、上游和远端 commit SHA。本结论不批准 main 合并，不恢复生产 Phase11 正常入口、全量测试通过或正式研究/实体资格。

审查者：实际 gpt-6-astra fresh reviewer；非本轮实现者。审查时 BASE/HEAD 为 `62a9b91116a6b314fa071eb3f8a6408524cd3d4a`。仅只读源码、计划、Git diff、原始 JSON/JUnit/events、归档文本及哈希；未运行测试、产品程序、SQL、网络或 Git 写操作。唯一写入为本报告和同名 JSON。没有新增 helper 或委派审查。

## 输入与范围复核

- `review-inputs.json` 的 51 项 bytes/SHA256 全部实算匹配；manifest SHA256 为 `a96dddc663e5659e9f1fb5731f62b7738fe75aa324d77a95d3cff4918b1c7e48`。
- adapter SHA256：`bb8bcc9f1cce4f5b04f724480f0910e6d0b2282ecaf89606f662d37cbefbfa55`；新测试 SHA256：`94abf15b0f4369318d37ef91c02d20e20d3c40110ea9f4eda03f8a579fb47c8a`。
- 独立重算原 1309 个源 pins，仅获准 adapter 不同；final stage 1310 个 pins（包含新增测试）全部匹配。69 项冻结输入出现项全部匹配。只读 tracked diff 除 gitlink 外仅 adapter；不把整个工作区声明为 clean。
- 独立比较 HEAD/current AST，`_draft` 与 `_path_hash` 未变；R419 plan.md/json 与 R418 原计划逐字相同。R419 只采用 first_round Tasks 1–3；R420 和 R421 补充范围与最终差异一致。Worker、repository、recovery、guard、默认 RGBD、TTL、旧断言不在修改内。

## 代码与证据联接

1. **真实性及失败优先级。** adapter `_collect_job_evidence`（约 454–635 行）核对当前 job/attempt、已结束 attempt、非空且全部已释放的 typed leases、本 job 路径内常规文件、完整 hash 集、终态一致性及 runtime_job 身份。legacy 成功还验证 ExperimentResult 的 experiment/run/scenario/mode/seed 和真实 `task_completed` 事件；没有把 `runtime_executed` 包装标记当作任务完成。`_runtime_outcome`（约 638–720 行）让三条必要 probe 均可否决成功，证据无效优先 FAILED/FINALIZATION，然后环境阻断、超时及任务义务失败。完成与 task_success 分开；SQL SUCCEEDED 本身不充分。
2. **发布门。** repo 获得实际 artifact_root；collector 调用现有公开 `get_publication_summary`。需要确认时必须 accepted，且 RGBD/VISION_CLOSED_LOOP 即便获得 NOT_APPLICABLE 仍要求确认。静态检查现有 repository 的 SQL/receipt/file 联接与 accepted 来源，未发现以 SQL 终态替代确认的新增旁路。当前原生覆盖是默认 RGBD/VISUAL_PLANNING 阻断及测试专属 legacy；本轮没有新的原生 closed-loop CONFIRMED 成功用例，不能据此声称该路线全面验收。
3. **模拟 crash lease。** helper（约 300–381 行）在公开 publication_guard 内 fresh 读 job 与精确 captured lease，核对 run/job/worker/lease/acquired/expires、INTERRUPTED、当前中断列表、未释放及真实 UTC expiry，再只 release 该 lease 一次并回读。repository 的 acquire 与公开 writer 同样使用该 guard，因此正常公开 API 的 owner 更换不能插入检查与 release 之间。未发现能释放新 owner 或未过期 lease 的本轮路径。七个反例是纯边界测试；真实公开 API 正对照来自独立 recovery。此结论只适用于 adapter 自建模拟 owner，不证明通用生产故障恢复已解决，也不声称完成新的跨进程竞争测试。
4. **SQLite 生命周期。** `_sqlite_summary`（约 755–782 行）以外层 closing 显式关闭自有连接，内层保留事务上下文和原 SQL 顺序，hash 在退出后计算。新测试持有真实连接强引用，COUNT/VACUUM/末次 checkpoint 的 sentinel 原样传播、close 恰一次；原生返回前与 observer 后 FD 分别采样。没有使用 GC、删除 DB、退出进程或清理借用连接来掩盖问题。
5. **指标与上层消费。** `_metrics_from_runtime`/`_metric_provenance`（约 785–914 行）把 task completion 连接到全流程事实；时长、质量及未测字段以 0/false schema 占位逐项 NOT_AVAILABLE，真实恢复/去重计数保留来源，研究资格固定 false。runner 实际 `_authoritative_for_thesis` 和 `_result_from_adapter` 消费测试验证干净 fixture manifest 与 source hash 不能解除隔离。占位不应解释为测得零耗时、质量失败率或安全事件为零。

## 原始验证核对

独立解析 38 个 stage 的原始 result.json 与 pytest-events.jsonl，逐一对照 validation-summary 的 return、started、call 和三阶段计数，未发现不一致。最终原始记录为 42 STARTED、42 setup PASS、42 call PASS、42 teardown PASS；JUnit tests=42/failures=0/errors=0/skipped=0，时间 27.483 秒。supervisor elapsed=28.528 秒，reaped=true，remaining_live/source_drift/ports_after 均空。两文件 Ruff check 与 format --check 的保存记录 exit=0，所记录源码 hash 与本次审查相同。上述为检查已有证据，不是审查者重新执行。

原 17 pure RED、4 native RED、首次 green-native 的 3P1F 均保留。最初三个只断外层 FAILED 的 PASS 不足以归因到特定损坏；最终测试 733–794 行与对应原始 receipt 已排除此掩盖：hash、identity、attempt、consistent=false 均只有 main 无效，分别出现精确错误，recovery/duplicate 有效。身份和 attempt 注入重新计算新 fixture manifest hash，故对应 PASS 不能只由 hash 差异解释。

直接读取最终 blocked/legacy/corruption 原生 receipt：默认三 probe 均为真实 BLOCKED_BY_ENV/RGBD_CAMERA_REQUIRED，invoked/completed/task/authority 为 false；legacy 只由测试 `_draft` wrapper 增加明确 input_mode，真实三 probe SUCCEEDED、executor return 与 task_success 为 true，authority 与硬件声明仍 false。测试未替换 Worker、SQLite、恢复或任务结果。

独立 recovery 的 RED 原档案保留旧 lease 空串/consistent=false；GREEN 原档案中旧 lease 于 `2026-11-04T00:19:16.826892+00:00` 释放，replacement 于 `2026-11-04T00:19:16.891852+00:00` 取得，先后顺序成立。第一 attempt INTERRUPTED、第二 attempt BLOCKED_BY_ENV 保留。最终资源 audit 的正确空串/NULL计数为 0，observer 前/后 FD 与 heartbeat 列表为空。旧 NULL-only “lease=0”结论已在 R419/R420/R421 报告撤回；旧原件未改，FD证据未被错误 lease 口径取代。

## 发现与交付边界

可定位、可复现的新增 P0/P1/P2 发现：**无**。未发现需要再开 Astra 修复轮的新增产品根因；不为审查中假设性边界擅自修改实现或测试。

报告没有把定向 42 PASS 推断为 4751 全 suite、5580 矩阵或旧 Phase12 模块已绿；明确保留历史 35FAIL/1INCOMPLETE、生产默认阻断、后续 RuntimeSpy/lease/API/性能等独立轮，以及真实模型、RGBD、相机、控制器与研究 gate 缺口。保守的权限/证据拒绝不等同于某条未覆盖运行路线已经成功。不能将 duplicate probe 的顺序 poll 对照外推为完整并发压力验收。

对冻结文本做了有限凭据特征检查，并阅读新增代码、fixture 和报告：未发现新增真实 credential/token/private-key 内容；本地用户名、主机名、/tmp 路径是运行元数据，不等同于凭据。此处不是对全部未跟踪 raw、DB 或整个仓库的秘密扫描。完整运行 DB、raw、凭据、模型与 SDK 仍在既定本地交付边界之外；manifest/报告/hash 不是完整远端复现包。

本审查未进行 commit/push，也未确认交付后的三处 SHA。实施者须按明确文件名单选择性提交，排除无关历史原件和 dirty gitlink，正常推送研发分支后独立保存三处 SHA 回执。若审查后的 adapter/test/输入发生变化，本报告的结论只覆盖这里冻结的版本，需按实际变化复核。
