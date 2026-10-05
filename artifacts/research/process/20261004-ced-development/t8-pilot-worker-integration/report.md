# T8 pilot worker integration — CPU source qualification

日期：2026-10-05。范围：`scripts/run_rgbd_pilot.py`、新增 `research/pilot_worker.py`、新增 `tests/test_pilot_visual_worker.py`，以及已协调授权的 backend 显式 XML 来源 SHA/加载器元数据修正。

本步骤将 v2 pilot 的直接执行调用接到真实持久化 worker source。软件资格检查通过；真实 Max、渲染、动作回合、边缘模型选择与研究冻结均未在本步骤运行或验收。

## 已实现的来源链

每个实际 case 在隔离的 `worker-runtime/<actual run_id>/` 下使用真实 `SQLiteSimulationJobRepository` 和 `SQLiteEventAutonomyRepository`。job 经 CREATED→QUEUED、仓储 `acquire_lease`、真实 `start_attempt`、LEASED→STARTING→RUNNING 后，才允许初始化物理后端。job/lease/attempt 标识来自真实仓储记录；未补造 attempt、租约活跃标志或 action-admission 标志。

job manifest 保存完整原始 pilot assignment、SceneSpec、网络安排、扰动、四周期候选、编译场景 SHA 和完整 worker source inventory。原始 `draft.parameter_overrides` 保存分配的 `supervision_period_ms` 和 `advance_physics_during_wait=True`，供持久化监督/等待 claim 桥接验证；没有改写周期、关闭监督或更换 control mode。

原始 UTC 起点取实际 attempt.started_at；单调时钟从 start_attempt 前采样。初始化、RESET 和 settle 均消费同一个原始 deadline。后台 heartbeat 只更新当前有效的真实租约，每次更新前后重新读取 job/lease/attempt join；取消、租约失效、source 漂移均停止继续执行。启动失败仍关闭已打开的真实 attempt 并释放租约；终态成功前再次验证当前来源，已释放的租约不能发布 SUCCEEDED。

## 场景、控制与 raw 来源

为保留 SENSOR/DYNAMIC 等原始 SceneSpec，离线编译器把目标、干扰物、目标区域、质量、摩擦、颜色、相机与光照参数写入同一校准资产族的实际 MJCF。之后通过后端标准 RESET 创建实际 episode；没有将所有 case 改成 S01 固定场景，也没有调用旧离线 apply_scene 的未观察 episode 替换。

初始化完成后借用同一后端的 capture，创建唯一 SkillExecutor，并在标准 RESET 前进入 v3 recorder。显式 model_xml 的实际字节 SHA 现在进入后端 source 元数据，同时准确标记 `MjModel.from_xml_string` 加载器。干净原始深度噪声保持旧 SceneSpec 路径的 0.0，再应用原始固定 sensor corruption。

`PerturbedCapture.transform_observation` 对已获取的 RGB-D 数据执行一次固定变换，返回实际结果、`rgbd.fixed-corruption.v1` 六字段 recipe 和当前脚本 SHA；它不重新拍摄或推进物理。root recorder 集成负责保留 clean SOURCE 和 derived ONLINE 记录，并核验变换字节。新 pilot 调用使用 v3 recorder；未把历史 v2 artifact 重写或冒充完整 v3。

在线 adapter 不再读取物理标签构造控制证据。commands/fault 日志仅在回合终止后发布；独立物理评价仍由 episode 的终止后路径执行。case result 保持 `accepted_success=False` 和完整失败分母。

## 验证证据

RED 已观察：7 个初始 qualification 测试因缺少 genuine persisted pilot worker 失败；显式 XML 实际 SHA 为空、加载器错误标记为 MjSpec、缺少原始监督配置、启动来源失败后遗留 RUNNING、已释放租约仍可发布成功等新增检查分别按预期失败后修复。

最终 bounded CPU 检查：

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest \
  tests/test_pilot_visual_worker.py tests/test_ced_pilot_stages.py \
  tests/test_research_pilot.py -q
45 passed in 13.30s

ruff check pilot_worker.py run_rgbd_pilot.py test_pilot_visual_worker.py backend.py
All checks passed!

mypy --follow-imports=silent src/cloud_edge_robot_arm/research/pilot_worker.py
Success: no issues found in 1 source file
```

mypy 另有现有配置的 unused overrides 提示（`ament_index_python.*`、`rclpy.*`），没有类型错误。

13 个新增 worker tests 使用真实 SQLite job/lease/attempt/runtime source。物理、provider、recorder 的回合效应仅使用 CPU fixture；pipeline configuration probe 替换 policy 构造以检查原始选项，不产生真实 action 权限、渲染帧、raw 完整性或研究成功证据。覆盖了共享后端/唯一 executor/RESET 前 recorder 顺序、初始化与 settle 取消、原始 timeout、不复活 lease、持久化 full assignment、source 漂移及终态 fencing。其余回归继续验证 480 分配、120 group、四周期 pairing 和全分母。

## 验收边界与 rollout 条件

实际运行仍必须具备被冻结的远程 Max role probe、当前真实 secret、未漂移的 cloud/edge/device binding、原始 assignment，以及持久化监督/等待 source claims。production `ExecutionPolicy` 的现有 guard 保持有效，直至 root 的真实 claims bridge 集成并资格验证；没有为测试关闭它。

此报告是软件来源资格记录，不是 actual calibration/native gate/nominal-loop 证据。边缘策略模型选择仍为 DEFERRED；实际 INITIAL、METHOD、FINAL 均未验收。本步骤没有付费 Max 调用、渲染或动作回合，也没有输出伪造的通过结论。

## 独立审查修正：startup 与已结束 attempt fencing

审查的实际 SQLite 复现确认两个遗漏：已获得 lease 后 `start_attempt` 在提交前或提交后抛错，原 cleanup 会遗留 LEASED 与未释放 lease；另一个参与者已真实终结 attempt 后，`__exit__` 会覆写其 ended_at/result/artifact_paths。新增检查首先观察到 3 个相应 RED；同 worker 获取新 lease 与新实际 attempt 的 takeover 保留检查已通过。

修正后 startup 在 publication guard 内重新 join 原始当前 lease 与唯一实际 open attempt。提交前失败保持 0 attempts，经已有合法 LEASED→INTERRUPTED→RECOVERY_PENDING→FAILED 状态清理并真实 release；提交后响应丢失读取仓储已提交的 actual attempt 再关闭，不补造 attempt。退出时所有 status/finish 写入前核对唯一仍 open 且匹配原始实际 attempt；若已结束或来源不唯一，则保留已有终态证据和 job 状态，只谨慎释放仍属本实例的原始 lease，并报告 source 失效。新的 worker/lease/attempt 不能被旧实例清理。

相同 bounded suite 最终为 `49 passed in 16.06s`；四文件 ruff 检查通过，pilot worker 的窄范围 mypy 无类型错误（仅前述现有 override 提示）。本次只修改 source cleanup/fencing 与对应 CPU 检查；SceneSpec、扰动、网络、周期、等待选项及研究验收边界保持原始要求。
