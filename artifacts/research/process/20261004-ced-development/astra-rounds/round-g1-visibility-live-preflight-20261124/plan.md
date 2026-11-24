# G1 现场 RGB-D 零步预检专项修改计划

模型 `gpt-6.2-astra`。本轮基线 `b4905bc14a9c4c83709fae4d59ed4f2a50348fe8`，承接视觉修复主计划基线 `742296625a618b216bbb4d9c1279ea3e22ee9f0d`。本文件只登记方案。

原始失败来自构建 `3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa`。f01-dual bootstrap 在旧物理步 120 采集，包内采集时间 `2026-11-24T14:47:50.299882Z`，载荷校验 `8d14ed544a01d49a3fbb7039698f99d3c3f8580164c9ecf1a4b608113d677b10`。文件摘要见表。

## 核对原件与预期 RED

- [ ] 复核 HEAD、上级计划和下列输入 SHA256，区分工作树文件和冻结构建副本。原命令 exit 1，在 occlusion_control 的 bootstrap_collection_tracker 构造 OpenCVTargetTracker 时抛出 initial acquisition unavailable: capture_time_not_fresh，尚未送入遮挡反馈。保留原 stderr、命令、失败目录及冻结运行时。仅用原包做离线像素读回和原时戳过期负控，分别输出回放与拒绝结果。

## 限定实施范围

- [ ] 仅变更 scripts/graduation/g1_visibility_trials.py 中的 preflight、occlusion_control 与必要的私有辅助，以及 tests/test_graduation_g1_visibility_trials.py。沿用 g1_visibility_runtime.prepare 的新不可变构建和原冻结适配器，不覆写失败构建。生产 tracker、servo、owner、控制器、几何和门限均冻结。输出仅进新开发预检目录与本轮步骤报告、阶段总结及公开摘要。

## 复核实际运行前提

- [ ] 沿主计划核对 919 原件与旧账本只读指纹，独占 EGL / MuJoCo、320×240 顶视相机 f33940579c533afe、同一解释器及版本、至少 16 GiB 可用、历史合格低位装配 SHA 和绑定新观察器的隔离构建。只在独立零步诊断目录取得设备锁、生成临时 owner/lease；与历史、正式及四个新摆放的任务账本隔离。缺依赖或输入漂移则保存诊断后停止。

## 开发零步现场阳性

- [ ] 固定历史 preregistered-0，位置 (0.45, 0, 0.035) m、yaw 0 rad、seed 24113040，依据旧资格 both 行。复用 g1_dual_probe 的 config、质量绑定、reset 和 capture 及真实 registered target/owner、OpenCVServoFeedback 路径。新进程在同一已绑定 scene 现场按原接口逐次采 bootstrap、initial-target、servo-reference 和 current，保留设备产生的 frame ID、两类时钟和步数；各次 capture 都在 0 步。复核已登记 ID7/8、有效目标、owner 与当前包身份、注册和伺服结果、零运动派发；保留原图、日志及采样耗时。禁止用旧图刷新时间、复用误标为新帧或将历史正式 f01 当作新开发摆放。

## 建立可归因的全遮挡对照

- [ ] 从同一次现采条件产生无遮挡阳性和全遮挡诊断，对负控同时封存基础 RGB-D 与遮挡 RGB-D，并明确遮挡生成方式和深度来源；阳性与负控分别独立初始化相同上下文。比较实际注册源、场景、相机、时钟、采集顺序和 source_step。优先沿已合格 g1_dual_probe 的零步独立采集与静态 tracker 绑定约定，验证真实 servo/registered target 拒绝。若 hold 的前置条件需要递增步/采样时间，则将附加的时序对照预登记为测试时钟的独立软件测试；正负两臂同一时钟策略、同一源步映射，记录原时戳、测试输入、原始模拟步数、映射及原因；现场零步评估只使用真实来源。可以在真实采样满足控制器约束时直接验证 hold，禁止改写历史包或虚报物理步，禁止用 mock 伪造视觉拒因。

## 核验预检与报告

- [ ] 用项目解释器运行 tests/test_graduation_g1_visibility_trials.py 并运行既有视觉/回放兼容测试。新构建从正常 CLI preflight GENERATION 执行。在相同上下文下，无掩码正控须实际到达预期反馈阶段以排除时间/源步/身份早停，遮挡负控须检测不到已登记码，记录精确视觉拒因及对应包 SHA。原控制器 monitor_hold 触发恰一条 accepted hold_current_joints、零运动目标/零运动派发/零物理推进，记录命令差、session/provider 采样记录和终止原因。时间过期、源步、校准、所有权、延迟或目标变化拒绝均须单列，不能充作遮挡通过。若正控、拒因、实际零步或指令审计无法核实，就停在未放行并保留原件；如追加测试时钟结果，分栏给出现场观测与软件覆盖。

## 放行边界

- [ ] 归档全部尝试、RGB-D 双摘要、采样/运行环境、命令与返回码、前后状态、私有清单与公开报告 SHA；分别给出软件、现场零步、历史开发动态、正式研究、实机结果。专项仅修正零步预检，动态历史试跑须待主计划 778 帧与 8 个首拒、其他离线门槛和专项预检全部放行后另行按主计划启动。本专项不发放四个新摆放或正式/实机试次，不调用任务模型。新增根因、范围扩大、计划外失败应保留原始证据并暂停关联工作，提交下一轮 Astra。

## 输入文件及 SHA256

工作树相对路径如下。私有原件在本地按清单保留。

| 文件 | SHA256 |
|---|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-live-preflight-20261124/preflight-stale-command.public.json` | `3111929d80a40b5083f508a76a55c050b715309ddc2fb6c3e51841f00cc49329` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-live-preflight-20261124/preflight-stale-original.stderr` | `b16ad7f73b18d20d1fee1de59b72f07809800a3908dfc5e175f399f82b525af7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-pose-repair-20261124/plan.md` | `25277830977fd0cab099d2fc074056e5ae298b5baa7647c522ed2d9dcd36e857` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-pose-repair-20261124/plan.json` | `9fe2d5f7a514a62ebdac454107360f9077a71feb9809b6e93e02a4c8e15c3ef7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-pose-repair-20261124/sampling-rule.public.json` | `035cf1eb65dc0a727411509047a5f78a0c04a6babee866cda0b919864ee79493` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-first-refusal-dual-marker-20261124/zero-step-probes.public.json` | `e8d1cbee3e655bfb8eb2daa54ed4236fa738e312ef9e2ce7b7cbc91773931c55` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-dual-bootstrap-evidence-20261124/bracket-qualification.public.json` | `2137a059084ede9a7204488920f6903d642044fa4e4946b4354c98c702d666e9` |
| `experiments/results/g1-formal-paired-20261124/trials/f01-dual/instance/pixel-index.json` | `4dca5738a71a884d1e5f55745931f41b4aa4b65780de6b7157cc4fee7d08f2a3` |
| `experiments/results/g1-formal-paired-20261124/trials/f01-dual/instance/frames/0001.json` | `5296e53ef8441e2a39f7ab83a129def51d9673972a916ee9590cb191f0749d6e` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/runtime-build.json` | `3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/assets/robots/franka_panda/scene_g1_development_dual_id7_y100_id8_x100_low_bracket_v2.xml` | `a0bf24bdf2c7142e9aaeebdaf5dec02255bf06885dde0e2e56f009aaf89f9803` |
| `scripts/graduation/g1_visibility_trials.py` | `3bdc5a7732275b4a48057710c4b14d63f92d2e22d6b74357828d630c845555b8` |
| `scripts/graduation/g1_visibility_runtime.py` | `fa92bfaeef89b82a88e0654e2966260d2c947dc6df82ddfccc92ba34bb83220d` |
| `tests/test_graduation_g1_visibility_trials.py` | `e23991b7678bb9eaff9ae5f60c9c07250ca8ed9d8647737eb177dc50e4e807e2` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/scripts/graduation/g1_visibility_trials.py` | `3bdc5a7732275b4a48057710c4b14d63f92d2e22d6b74357828d630c845555b8` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/scripts/graduation/g1_dual_probe.py` | `a1f0586834a134d91e7c9c22fb644f72a12575e1e3b6ffee57ef7807d5daf7b0` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/scripts/graduation/g1_dual_runtime_adapter.py` | `14e0a1aeafc93407370847df7bde2304650640cc2f04f2b3fe3003fffab0e1cf` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/scripts/graduation/g1_dual_observer.py` | `a6c919b82e769d432c4ce425b4f44c6b8c228bff8ef4b1d7787f28689c416db3` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/scripts/graduation/dynamic_vision.py` | `1c0a069f578e3107c473566db4fb607b3bfab919e6df4faa157aa84dd503665e` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/src/cloud_edge_robot_arm/research/native_collection_grounding.py` | `fd7c8052cb936e12a90be858f826a8038970404a4018ecbc90eeb26a6beb7aad` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/src/cloud_edge_robot_arm/vision/servo.py` | `991f67035706026b5219b43e398f020be98fabba311246846a30bb9372962768` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/src/cloud_edge_robot_arm/vision/tracking.py` | `9c8cf00659dd3542d21f108df21a1880b3b540d07e9fd2fcd7ce020a1d6d876b` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/3ebe455d2af191ccb196f19197e5571e4f7205218eb574e682750494f69d0efa/runtime-source/src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py` | `71218ee666b8b90772cc9e3a03bab93c45c57d3ae6017c8ec734e9dd3fb13ff8` |
