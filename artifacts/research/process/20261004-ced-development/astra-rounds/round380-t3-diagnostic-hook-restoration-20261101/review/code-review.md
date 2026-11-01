# R380 独立代码与证据审查（终态复核完成）

结论：**APPROVED_R380_TEST_SCOPE**。新增 Critical 0、Important 0、Minor 0。原 R376-CR-1 已按本次实际 Astra R380 计划修复，短合同与完整 confirm_timeout 终态复核通过。可释放共享测试源进入 R381；commit_close 仍为独立 NOT_CLOSED。

## Strengths

- `tests/test_rgbd_runtime_control.py:178` 在 create_job 之前构建完整 ExperimentManifest，保留原 draft truthiness 默认行为、synthetic test/hash 标识、任务/租约/timeout 参数；配置由独立 deepcopy 快照生成。产品验证和公共读取未改。
- `tests/test_operational_t3_fixture_contract.py:18` 三变体使用真实持久任务和真实 service.get_run；验证 manifest/任务字段一致、嵌套调用方修改及读取副本修改不影响持久快照。仅抑制实例 dispatcher.start，未伪造公共结果。
- `tests/test_operational_runtime_closure.py:5138` 的 configure 将内部 scoped 交给 terminal fault，诊断 D 与故障 F 同栈安装，实际顺序 O→D→F、撤销 F→D→O。helper 在正常及异常退出后验证 entry 方法 identity，未把诊断转移到长期外层来掩盖泄漏。
- `tests/test_operational_t3_diagnostic_contract.py:15` 直接调用真实 installer/owner helper/故障 helper 和实际 MonkeyPatch，覆盖正常、sentinel 异常、同进程重复周期。委托合同另核对 target/non-target 一次调用、参数/返回对象、原异常对象及 traceback、active exception 记录；SimpleNamespace/spy 明确只是 instrumentation 单元边界，未冒充租约授权或 broker 验证。
- 对 HEAD 及 R380 冻结输入的 diff 显示：原 terminal fault 内容、公共读出、negative/corruption/legacy/reopen、SQL/receipt 等原断言未删除或放宽。callback 原异常仍被保存后重新抛出；诊断委托不捕获/替换其原异常。
- 新 bounded_stage 使用新目录和 exclusive 证据写入、明确环境、monotonic child cap、剩余 round 预算门槛、subreaper、PID starttime 核验及有界 TERM/KILL/reap。cleanup_active 使清理区间的重复取消只记载而不再次抛出；这是静态判断，未做信号压力实验。冻结 R376 runner 的 SHA 保持不变。

## Issues

### Critical

无新增。

### Important

无新增。原 **R376-CR-1** 标记 **RESOLVED_BY_R380_STATIC_SHORT_AND_LONG_RUNTIME**：复现、修复及原 confirm_timeout 完整终态见下表。

### Minor

无新增。原 **R376-CR-2** 属冻结 runner 的历史静态风险，原文件未改；新 runner 的 guard 不能升级为重复取消的实验验证结论。

## 已有运行证据复核

本席未运行测试；以下来自只读 JUnit/stdout/result/prerequisite/source snapshots。

| 阶段 | 原始证据结果 | 边界 |
| --- | --- | --- |
| R376 fixture RED | 3 FAIL，均为真实空 manifest 缺少六字段 | 合法输入合同 RED |
| R376 fixture GREEN | 3 PASS | 默认、定制、继承工厂及公共读取 |
| R376 shared smoke | 3 PASS | 取消/失败既有语义保留 |
| R376 五个长节点 | confirm_timeout、prior_bound、memory control、sqlite control PASS；commit_close FAIL | 每阶段终态、reaped=true、remaining_live=[]；独立失败保留 |
| R380 diagnostic RED | 2 identity FAIL + 1 delegation PASS，2.044 秒 | 两项失败均为 terminal invalidate hook leaked，非导入/环境错误 |
| R380 diagnostic GREEN | 3 PASS，1.639 秒 | 正常/异常恢复及委托合同通过 |
| R380 fixture GREEN | 3 PASS，3.151 秒 | manifest 合同未回退 |
| R380 confirm_timeout | 1 PASS，pytest 246.19 秒、driver 247.127 秒；无 skip | 原全断言、真实 fault 四事件、same-process identity 与清理均通过 |

R380 已结束的四阶段均 accepted_prerequisite=true、trace/profile 四项皆空、源前后 1051 项完全一致、errors/signals/cancellations/remaining_live 为空、reaped=true。四项 argv 与 Astra 命令模板一致，fresh stage/60,60,60,600 秒预算及同一新 round_end 匹配，SIMULATION_RUNTIME_DB 缺省。当前 HEAD 保持 `28ac315c2af8567b377e6e2cc3ee5acb9cda4677`。

R380 计划 76 个输入中，75 项仍与原 pins 完全一致；唯一变化是计划允许编辑的 closure。新增诊断合同 SHA 与 RED/GREEN snapshots 相同。把当前 configure 的单行 shared-owner 赋值逆变换为保留旧 owner 后，静态重建的 RED closure 为 316418 bytes / `34549bb8629ab6389630f3c3667fa313bf617958b9d11bb1de22f114a24198d3`，精确匹配 RED source-before pin；此项未执行代码，也未改写源。新 legacy-goldens 与冻结 R376 副本逐字节一致。审查文件与证据 SHA 清单保存在 JSON。

完整 confirm_timeout 的真实 fault 顺序为 ACTUAL_TERMINAL_REQUEST_DEQUEUED → ACTUAL_MAIN_RPC_TIMEOUT → LATE_BROKER_RESUMED(cancelled=true) → ACTUAL_BROKER_DENIAL；fault.fired=true。case 记录 675 个资源、cleanup_errors=[]、observers_restored=true，公共结果 SQL=SUCCEEDED、confirmation=UNCONFIRMED、accepted=false，23 份 unconfirmed 文件保留。诊断 checkpoint 到达 after_poll_assertions_completed、poll_returned=true、exit_exception=null。原 long test 的 owner helper finally 在 _b_t3_case 写入与 pytest PASS 前真实执行，因此本次 same-process invalidate identity 断言已完成；没有依赖进程退出代替恢复。

## Declined to judge
- R381 commit_close 根因修复与最终闭合：R376 原始失败仍为 NOT_CLOSED；后续 Astra 独立轮负责，本次不修改/测试。
- R377 浏览器、R378 标记登记、R379 资产 manifest 的窄改：尚未纳入本次请求的已实现范围；仅将共享 runner 作为 R380 已固定输入审查。
- 原 R376 runner 重复取消、以及新 runner 的主动信号压力行为：本席禁止发信号，计划明确未授权压力实验；仅报告静态实现，不声称实验通过。
- 受保护 local_temporal 候选、两份 temporal 测试和嵌套 workspace 质量：用户明确排除本轮交付；其已登记字节 pins 保持一致。
- MuJoCo/硬件/云端、UTC 联合 600 秒及正式研究验收：本轮证据仅为 CPU 软件验证，不能据此外推。
- Git 提交/推送和远端完整复现包：本席禁止网络和 Git 写；无此项独立验收结论。

## Recommendations / Assessment

**Ready to merge? Yes，限 R380 测试修复范围。** 静态 diff、短 RED/GREEN、manifest 回归以及原 long confirm_timeout 的完整断言和清理证据一致，没有新增阻断问题。R380 诊断修复的软件验收已闭合，可在登记本 review 精确 SHA 后释放共享源到 R381；后续交付保留 commit_close 未闭合和 CPU 软件边界。

使用 `superpowers:requesting-code-review` 及其 reviewer 模板完成独立审查。仅写本 review Markdown/JSON；未进行产品导入、测试、信号、网络、Git 写或改动旧证据。


终态复核截点（UTC）：2026-11-01T13:58:07.515539+00:00。
