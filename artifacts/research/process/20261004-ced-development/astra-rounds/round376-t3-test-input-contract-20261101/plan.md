# R376 T3 Test Input Contract Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 按本计划执行；用户已选择修复方向并授权，无需追加设计审批。

**Goal:** 修复 T3 工厂创建任务时缺失完整 manifest 的输入合同，让公共读取和原故障断言真实执行。

**Architecture:** 在实际创建任务的 fixture 源头补齐 ExperimentManifest；不修改产品读取和验证。以短合同 RED/GREEN 加原 5 个独立目标节点验证，保留尚未知根因的 commit_close 真实结果。

**Tech Stack:** 现有 Python/.venv、pytest、Pydantic、SQLite，软件 CPU factory。

**Spec:** 用户“先恢复测试输入与版本登记的一致性，让关键场景真正执行到目标位置”、根 AGENTS.md，以及同目录 plan.json 的输入 pins/命令/预算。

## 基线与范围

实际 Astra：`gpt-6-astra`，HEAD `28ac315c2af8567b377e6e2cc3ee5acb9cda4677`。沿用现有 checkout，不切工作树、不装依赖。保留未提交 local_temporal（SHA `c8a5a5a45d80a9123708125e18528b5b083c388ee389a81e44536ae84dad5f9c`）、两份未跟踪 temporal 测试、两个嵌套 workspace 和其他用户文件，不重置、不混入交付。

本轮只改 `tests/test_rgbd_runtime_control.py::_queued_closed_loop_worker` 的 manifest 生产，新增 `tests/test_operational_t3_fixture_contract.py` 短回归，并在 closure 的 `_b_t3_exercise` 内限定补充原异常/触达留证。不改 phase11.1/_draft、rgbd_runtime、lease_handoff、software_factory 或产品。标记版本绑定、浏览器 input_mode、资产 manifest 分别后续轮处理。

## 证据及判断

R374 p6_t3_06/07/08/09 在真实 `_run_record` 中验证空 `{}`，缺少 manifest_id、normalized_config、source_commit、source_tree_hash、run_count、reproducibility_hash 六字段。调用链为 closure→software_factory→_cpu_visual_worker→_queued_closed_loop_worker，最后 create_job 未传 manifest；正常产品 create_run 会传完整 model_dump。四项既有失败可复用为长路径 RED，不再原样重跑。

p6_t3_05 commit_close 在 fault.fired 前 INTERRUPTED，原错误仅有 operational_epoch_ended/original worker poll ended，未知原始异常；不得宣称已证实同根因。五项原耗时约 226–245 秒。原审计、stdout/JUnit/events/result、插件/golden/源文件的 61 项路径、bytes、SHA256 见 plan.json。

## 实施步骤

- [ ] 复核 HEAD、输入 pins、受保护脏文件及实际执行权限，记录本轮源基线和新目录。复制原 golden，字节与 SHA 不变。
- [ ] 新增 `test_queued_fixture_has_complete_manifest`，参数 queued_default、queued_custom、inherited_software_factory。不 poll worker；验证真实持久任务的完整 manifest、字段与实际 draft/任务一致、调用方修改不影响已存快照，并用明确临时 DB/root 的真实 service.get_run 读回。只按既有 T3 方式抑制 dispatcher.start，不 mock 验证或返回值。一次 60 秒 RED 必须是预期缺字段；导入/环境失败不是合法 RED。
- [ ] 在 queued fixture 插入前构建并序列化 ExperimentManifest：独立 effective draft 配置快照，run_count=1，manifest/source/repro 字段与原 job fixture 值一致。保留原 synthetic test/hash 标识并明确是软件 fixture，不伪称真实版本证据；不更改 draft 默认/覆盖、租约、状态或超时，不事后补写数据库。
- [ ] closure 仅窄范围包装此 worker session 的 invalidate，记录真实 reason 和活跃 sys.exc_info traceback，原调用委托一次且不改变参数/结果/异常；finally 在本次 case 新文件保存触达点及真实任务结果。保留原 callback 错误。禁止新增 trace/profile、置真 fired/accepted、改产品异常处理或跳过任何旧断言。
- [ ] 一次短 GREEN（60 秒）和一次共享 fixture 取消/失败 smoke（120 秒）通过后，按 plan.json 启动四个 manifest 故障节点及最后一个 commit_close，每节点独立一次 600 秒，串行；新问题只记录，不修。受影响修复暂停，独立节点可完成。
- [ ] 生成步骤报告及目标触达表，审查源差异与证据。仅选择已验证的测试改动及精选证据提交/推送研发分支并核对本地、上游、远端 SHA；不广泛 add、不纳入性能候选/两份未跟踪测试/嵌套 workspace。传输阻塞如实记录，不 force push、不修改 TLS/Git 持久配置。

## 运行前置、命令及额度

具体 argv 和环境模板在 plan.json，直接由已成功进入行为的 R374 invocation 派生，真实 stage_id 为 R376；`final_new23` 仅是旧兼容标签。R235 插件保持原 pin，startup receipt accepted=true、profile/trace 前置成立；保留 R223 resource/case、R158/R175 sinks。每尝试使用全新绝对 DB/artifacts/cache 路径，删去模块级 `SIMULATION_RUNTIME_DB`，保留隔离 MODEL_CONTROL_DB/DASHBOARD_ARTIFACT_ROOT。不继承凭据，不运行云模型/硬件，不启动网络服务。

parent 报告实施会话 workspace-write/network restricted，本规划会话工具声明却是 danger-full-access/approval never；执行时必须核对实际权限，不能假设任一旧环境。明确环境拒绝只在工具允许时申请对应 escalation；不得把拒绝记作产品失败。仅允许一次在行为开始前明确环境拒绝的替代启动，计入本轮总额；行为已运行则不可用此例外重试。

8 个阶段：60+60+120+5×600 秒，加各 15 秒清理共 **3360 秒（56 分钟）**；新 R376 总墙钟 **3600 秒**，不追溯延长 R373/R374 八小时账。每阶段 TERM 宽限 5 秒、清理 15 秒，拥有组身份核验、kill/reap 与回执；无自动重试、不并行。剩余额不足当前阶段及清理则 NOT_RUN_BUDGET。既有约 240 秒每长节点仅供预计，不放宽原 600 秒界。

## 验收与未覆盖风险

短合同覆盖默认、定制、继承调用及独立快照；共享 smoke 保留取消/失败语义。四个已知节点须整节点通过、原 public/rejection/corruption/legacy/reopen 断言全部完成，案例 assertions_completed=true。commit_close 必须真实触发原 SQL/连接故障并通过原断言；若仍未触达，保留新原异常与实际进度，标 NOT_CLOSED，下一轮 Astra 后才修，不将输入修复包装为全 T3 已通过。

保存完整 stdout/stderr/JUnit/events、退出/耗时/超时/清理、源前后、前置及原异常。DB 只在进程结束后清单或复制静止快照审计，不修改旧 DB/WAL/SHM。可独立交付已验证 fixture 改正，但明确 commit_close 未闭合。软件 CPU 结果不替代 MuJoCo/硬件/云端真实证据，不宣称全流程通过，不变更原 UTC 合并 600 秒验收，本轮不重跑 UTC。

本轮规划只读调查及写计划，未实施、测试、导入产品、发信号、联网或修改 Git。
