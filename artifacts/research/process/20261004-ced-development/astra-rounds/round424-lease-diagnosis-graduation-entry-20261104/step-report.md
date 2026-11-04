# R424 租约问题排查与毕业设计准入检查

当前可以继续 **T3b/T7b 主线的受限开发和证据补齐**，无需等待所有格式、中文规范、可选后端或全仓测试清零；当前证据尚不足以进入 B0 实际筛选、INITIAL 或正式实验。本轮按实际 `gpt-6-astra` 的限定计划完成诊断，没有修改生产代码、原测试或原断言，也没有把 5 项失败改判为通过。

## 版本与执行

输入分支 `research/20261004-continuation`，HEAD `78f36fbaf43d6bbe3b50c40d09097f75895d72ab`。实施前、后全部 52 个计划输入 pin 匹配，1311 个运行源文件（其中 src 406 个）字节保持。实际解释器、驱动、事件插件及记录型 trace 均已冻结。详见 `preflight/input-verification.json`、`preflight/target-manifest.json`、`postflight/source-integrity.json`。

全部运行使用独占新数据库与 basetemp，禁用真实 motion，没有模型、付费服务、secret 或旧数据库内容查询。原 5 节点各新进程执行一次，零重试；另执行 1 个独立 guard 探针，包含原 helper 和预初始化对照两个子场景。总执行及清理 31.075 秒，低于 Astra 300 秒上限。

| 阶段 | call 结果 | supervisor 秒 | 解释 |
|---|---|---:|---|
| lease-01 跨进程 guard | 原预期 FAIL | 7.510 | Queue.Empty 重现；独立探针补构造与持锁握手证据 |
| lease-02 expiry 与替换 owner | 原预期 FAIL | 3.004 | active expire_leases 事务内的非登记嵌套 mutation |
| lease-03 expiry 与 heartbeat | 原预期 FAIL | 8.009 | active expire_leases 事务内第二连接写入 database is locked |
| lease-04 cancel 与 handoff | 原预期 FAIL | 3.005 | active request_cancel 事务内的非登记嵌套 mutation |
| lease-05 stale retry | 原预期 FAIL | 3.004 | active retry_job 事务内的非登记嵌套 mutation |
| 独立 guard 握手探针 | PASS | 5.007 | 两种时序均验证互斥及释放后进展，两个工作子进程 exit 0 |

6 个节点各一次 collection/STARTED，setup 与 teardown 全部 PASS；5 个原 call 仍 FAIL，独立探针 call PASS；无 skip、error、incomplete。全部 supervisor 自然结束、reaped，无剩余存活 owned 进程、强制信号、取消或源码漂移；各阶段汇总 stderr 均为 0 字节。这不是 5 项修复后的 GREEN，也不是全量通过。完整映射与原始证据 SHA 见 `validation-summary.json`。

## 根因与仍未覆盖的行为

**H1：测试握手循环，有独立原路径运行证据。** 原测试在父进程持有 publication_guard 时启动子进程并等待 waiting。子 helper 必须先完成 SQLite 仓库构造；构造的 `_initialize` 也要拿同一 guard，waiting 则在构造之后发出。探针实际调用冻结原 helper：子进程停在真实 flock 前，父持锁期间没有越过该行；父按预定时序释放后，构造返回，waiting/acquired 到达，child exit 0。预初始化对照先完成构造再竞争同一锁，也正确等待父释放后取得锁，child exit 0。

原 lease-01 测试在 finally 自行 terminate 子进程，未导出它的准确 exitcode；该原节点的 child exit 继续记 UNKNOWN，不能用独立探针两个 exit 0 反推。原节点的 trace 过滤器未记录构造/guard，空 trace 不伪称已取得其 child 栈。H1 的运行确认范围为独立受控原 helper 路径，与原节点静态路径及 Queue.Empty 一致；不据此排除原节点其他启动时序影响。

**H2：三项竞态注入违反当前事务与 caller 契约。** 实际 trace 显示 `_transactions.connection` 存在且 `in_transaction=true`，owner operation 分别是 expire_leases、request_cancel、retry_job。race/_handoff 回调调用 update_status_cas，真实 caller 不属于登记的同 job 从属写入，被既有规则拒绝。失败发生在原目标 CAS／owner 断言之前；它们没有有效检验原本想检查的替换、取消或重试行为。没有放宽 allowlist，也不能据拒绝正确推断合法并发行为整体正确。

**H3：心跳注入制造自身写锁等待。** 独占新库中，refresh_before_cas 抛错时父 writer 仍在真实事务内；trace 同时记录第二连接确为不同对象。冻结代码的 BEGIN IMMEDIATE 覆盖扫描与更新，回调通过第二连接写同库，却必须等回调返回父事务才能结束。该注入时机不符合真实序列化边界。没有调大 SQLite timeout、缩小生产事务或移除锁。

上述记录见 `diagnosis.json`、各阶段 `trace.jsonl`，以及 `validation/probe-guard-handshake/guard-evidence/`。下一修复须由新的 Astra 计划重建合法边界上的握手／竞争测试，并保留真正非法嵌套调用的负例；不能通过放开生产授权迁就旧注入。

## 下一阶段的进入条件

| 下一步 | 当前判断 | 可审查的放行条件 |
|---|---|---|
| T3b/T7b 受限开发 | **现在可以继续** | 复用已有校准、角色和消费者接口；每项新缺陷先 Astra，限定修改，相关定向验证与来源可核对。不能以获取证据为由绕过动作门。 |
| T3b 当前 Max 实测 | 当前绑定证据待核验 | 选择用户指定的实际 profile/角色及预算，当前源版本的双图 wire、解析、缺失目标拒绝和晚到／取消边界独立通过。checked-in profile=null 不等于运行 store 无凭据；本轮未探测该 store。 |
| T7b native 动作／效果验收 | **仍缺实际来源与接入** | 独立实际校准来源→冻结应用索引／rolebinding→实际 native 消费者；有效几何／运动与连续效果证据，UNKNOWN 不放行。保留身份、标定、时序、现控制器及 SafetyShield。 |
| T8a B0 筛选 | 等当前 T3b/T7b 验收 | 120 个独立 selection 组配对扫描 0.5/1/2/5 秒，保留全部 480 周期—组结果；候选静态成功≥90%、整体≥80%、安全违规≤1%。全部不合格则 NO_FEASIBLE_BASELINE。 |
| T8b / INITIAL | 尚未具备当前完整证据 | 合格 selection＋完整固定机会／200 组实际故障教师证明＋另 120 未用组 foundation＋独立完整预算。foundation 复现同质量门；Tcap、角色、来源核验后 INITIAL CLI 实际接受。 |
| 方法／功效／FINAL | 还需要研发与实际验收 | INITIAL 后完成风险／公平基线／规则决策／有界恢复的实际来源接入；冻结完整方法和 provider，再用另 120 组只估功效，验真后确定 N 并接受 FINAL。 |

当前实现有两个直接可核对的主线缺口：`vision/action_evidence.py` 仍把几何误差界与运动界设为 None；`vision/native_calibration.py` 已有软件，但固定应用索引 `configs/research/native_calibration_sources.json` 当前 ABSENT_OBSERVED，原生提交路径尚不能由它取得合格实际界。另 `scripts/run_rgbd_pilot.py` 的 power 分支明确标记 method runtime 与实际功效来源验收未集成，即使已有 INITIAL/method 文件也不会因此获得完整功效先导。

下一轮研发应优先收口本轮三类测试前置契约，并转入“独立实际校准来源→应用索引／角色绑定→native 消费者→连续效果证据”的最小主线交付；T3b 当前角色配置与来源只读核验可以同时推进。旧 4807 帧 OBSERVED、历史 Max 35 次 HTTP200、离线教师成功、fixture VALID 都不替代这些出口。具体开发范围与实际采集前提需下一 Astra 计划明确，不能先填常量或借用在线真值放行动作。

## 其他问题与研究边界

R419—421 的回执真实性与资源生命周期定向交付、R422 的原 22 项测试契约／47 定向 PASS 保持有效范围；R413 全量仍是被测 ab18 基线的 4709P/35F/6skip/1INCOMPLETE，不能减去本轮或以前的定向数量生成新全量结果。

生产 Phase11 固定 MOCK 的输入意图、Phase12 原 2 FAIL＋1 INCOMPLETE、事件复现、API 生成契约、UTC 性能及治理项仍在各自队列。UTC 两后端 4502.509 秒未达原 600 秒线的事实保留；本轮没有跑性能、浏览器或全量。R413 已有 ETEAC/PCSC MOCK 自然结束和浏览器 42P/1 原 skip，不能继续照搬 11 月 2 日旧权威页的旧待办。

只有待走入口实际依赖的来源、租约、回执、安全或统计问题才构成其前置；不必先清空所有 Ruff／格式／中文治理问题。边缘模型选型后置，规则／成本 provider 如实验收即可继续；Isaac、G5、腕部相机是可选扩展。云端用户方案、OpenCV、可见标记、顶视相机和现控制器保持。真实硬件仍 NOT_STARTED，S3/S4 LOCKED。

## 保留与交付边界

原失败、旧 raw 和原实验字节保持；6 个新 basetemp 全部建立本地 create-only 副本，14 个普通文件、888832 字节，复制前／副本／复制后哈希一致，原目录也保留。完整新 DB、raw、stdout/stderr、全量本地保存清单保留本地；精选源码、报告与可审查事件／JUnit／终态证据按明确清单交付，不能称完整远端复现包。

执行裁定：沿用既有研究 checkout 和诊断计划 D0—D5 段落以保持输入一致，隔离依赖前后 source pin；只执行计划内诊断，不声明生产 TDD GREEN 或全量验收；根 AGENTS 优先要求保留 scratch／raw，代价为本地占用增加。详见 `progress.md`。研发分支 Git 三处 SHA 回执在交付完成后另存；main 不合并。

配套：`plan.md/json`、`astra-entry-assessment.md/json`、`diagnosis.json`、`validation-summary.json`、`postflight/source-integrity.json`、`postflight/raw-preservation-summary.json`。
