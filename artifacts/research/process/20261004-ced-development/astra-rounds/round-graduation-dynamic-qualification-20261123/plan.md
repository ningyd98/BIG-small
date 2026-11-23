# 毕业设计动态控制与视觉工程验证计划

gpt-6.2-astra / 2026-11-23 / 6416a6cc4b1b087c17cf1c738b202e8f28421e2a

静态/短程开发留出支持部分位姿下的空间观测，但不足以回答整段控制、0.5秒抬升/1秒落位窗口以及真实动态视觉失效如何在本机复现。

## 来源证据与假设

- B/C固定3个开发留出摆放、162帧中SUBPIX识别159帧。有效物体顶心误差P90=6.868597871mm，最大10.991378560mm；抽样中含轴向/侧视与同摆放重复测量。连续几何速度包络未获。
- canonical源使用 scene.xml、S01_NORMAL_STATIC seed31、离线预设TCP与现有接触控制。正控7次技能调用（move_above、approach、grasp、lift、move_to_region、place、release），额外120步和240步停留；默认不渲染RGB-D，只存阶段快照。5项现有负控为无接触、不可达、超时保持、急停、空手放置。阶段快照不能独立复验每一步。
- 冻结正式首组的8条准入中LIFT POST两项UNKNOWN，前3动作通过POST；6,240物理步/11,109帧，另外8组NOT_RUN，唯一正式claim已用。
- 原本机开发固定夹具可能完成抓放且控制保护反例按预期拒绝；独立逐步物理评价可能与原简化阶段断言不同，必须并列保留。
- 同固定轴向r593开发实例可从实际RGB-D和原有注册几何推导MOVE_ABOVE候选。真实准入、Shield、重观测和控制器各自可能在首动作前后停止。运动中连续可见或离散最大速度仍不能签发通用连续运动上界。

## 预分配与范围

六个canonical组件工况和一个独立真实视觉守卫开发实例。具体ID、初姿和技能上限已在同目录JSON预登记。

- 只增毕业开发诊断脚本、相应测试及公开小结；允许在 scripts/verify_rgbd_physical_skills.py 以默认关闭的显式只读审计参数接入现有正控。可等效单独注入明确的observer factory，保持原技能调用/动作回执与CLI默认语义。不得修改产品src、算法、控制器、SafetyShield、正式登记资产、准入事实或阈值。原始证据不改写。
- 两类来源分开计。canonical为固定TCP真实物理与保护控制；新r593实例为真实图像派生目标、实际组件准入后才尝试动作的独立开发案例。零任务模型，固定的是技能意图/初始场景，执行TCP不从常量或真值赋值。未实际经过的原生权限/Shield/模型路径均如实标注。

## 实施与审计

### 1 签发开发批次与证据路径

- [ ] 复核全部输入。先实现小工具及软件测试，再在任何上述物理运行前写不可覆盖 allocation.public.json，冻结上列7身份、一次/身份、图像尺寸/相机/几何/流程、实际工具/控制/读出源码与两资产SHA、依赖版本、模拟步长、EGL、可用资源、磁盘、隔离新输出路径及UTC。预分配60分钟总墙钟及至少1GiB可用私有空间；若需中止保留前缀与未运行。不得用既有claim，不重试失败格。 动态视觉组件采用现有真实准入管线，实施前封存被选入口、原生适用前提、超时与固定调度，不得换用下层入口绕过其拒绝。
- [ ] 预检可跑不带物理命令的导入、EGL上下文和资产几何注册，验证独立ID不同于历次实验，计数6+1。预计数分钟至数十分钟；已在运行的独立其它任务不受影响。

### 2 原固定抓放与五保护负控

- [ ] 使用canonical原main顺序、原seed、未标记原asset、原固定目标及原timeout/负控。允许CLI新增仅审计输出路径；正控backend.reset后记录step0，并用公共 observe_physics_steps 保存每次真实mj_step的detached PhysicsStepObservation。阶段进入与退出保存步号/UTC/结果；对两处原dwell独立记录开始和结束。控制不读这些记录；独立评价等轨迹封存才启动。其他5项照原入口，记录逐项实际返回/错误、步数、漂移、接触及原断言。有动作失败仍按原函数返回或停止，记录尚未发生的阶段。
- [ ] 原canonical结果保留。逐步序列0..末步不漏重，以实际dt和sim_time核实。使用原CompletionCriteria、sample_physical_observation、evaluate_evidence离线从原始逐步文件重建全程。分别列原positive.passed、独立outcome/status、对齐特定动作的window。对lift返回到原+120区间及release返回到原+240区间取含两端121/241样本，逐步报高度差(注明reset与LIFT派发两种基准)、双指接触/夹爪开合、速度、完整投影区域/底面、失败达标步数、首个违例及最长连续满足秒数。保留起步瞬态；不得另选最佳窗口代替规定窗口。独立评价与原简化criteria冲突是有效科研结果。

### 3 独立r593真实图像接入控制

- [ ] 使用唯一新r593实例，登记轴向相机(0.35,0,1.4)、320×240、1/240s、物体在桌面默认姿态。采集真实step0的RGB-D，重建标记顶心/相机、物体及场地的注册，使用原collection_bootstrap_evidence、原标记/顶抓求解、区域/目标观测与现有resolved_step或确定性GroundingPolicy。记录源像素、观测SHA、物体顶心、解算抓取TCP、MOVE_ABOVE候选及其单位。使用真实具名开发组件路径、原契约及所需条件、时效、新帧、研究SafetyShield PRE/POST、有活动/取消/急停保护的生产技能接口；允许仅离线预登记意图，无模型回答或Oracle几何。首动作建议复用VisualServoSession与原技能接口，反馈必须逐次从新实际RGB-D重算，禁止lambda原样返回目标；所选已有组件的全部前置与时序照常核验。正常资格只允许前项PRE/POST通过后接着使用同一入口按登记顺序到完整抓放。若源拓扑缺必需owner/lease或生产条件无法满足，将实际调用返回的错误/原入口源码和缺少的上下文留档、保持和停止，不能用裸robot方法或伪造原生资格、替身回执或猴补正式登记绕过。即使第一帧拒绝也保留真实帧、候选若有、拒绝层与后续NOT_RUN；不换机位、方法、身份试第二遍。
- [ ] 预冻结原接口名称、契约、每个阶段门槛及运动观测网格。动作及停止全程用只读observe_physics_steps保存每个实际物理步，封存原反馈RGB-D/每个预定视觉期限和首末帧；若技能中无法由公开只读接口获取每个物理步RGB，不在observer回调内二次渲染，报告视觉实际频率、最大缺口及原因。像素决策封存后才以单独进程按同一episode/step/frame/hash联配物理真值，分别统计整段和动作窗口的有效/拒绝数、首末物体/TCP变化、误差P50/P90/max、邻帧表观速度。到达LIFT/RELEASE则考察原0.5s/1s窗口的实测序列；未到者标NOT_RUN，canonical物理结果单列。若未获正式误差界或采样间运动保证，即使组件到达TCP也保持原注册UNKNOWN。

### 4 单独复算、报告与研究余缺

- [ ] 写脚本及测试覆盖缺失一行/相邻步重号、错episode/跨资产、错误阶段窗、篡改帧、UNKNOWN保留分母；独立进程仅从私有落盘原件复算JSON并比对语义稳定输出，阶段窗口和简单计数另以直接枚举交叉检查。小型公开allocation、summary/verification、步骤报告与阶段总结，纳入论文/答辩现有结果（可增一表，原真实负结果保留），保留原件与命令/退出/环境/SHA。
- [ ] 区分固定技能成败、独立物理判定、带守卫的视觉组件动作、真实反馈率、停止位置、正式研究资格；同时给出从课题到下一步需新注册独立动态条件、误差与连续性依据、B0/研究批的确切缺口。公开文件无raw/数据库/凭据/权重；按父项目交付规则提交核SHA。

## 前置与验收边界

- 已存在本机MuJoCo/EGL、OpenCV、Pillow、同版本原资产/标定、读取及独立输出权限。超时/资格拒绝/视觉缺帧/条件不满足是预期观测，保留分母与末个实际阶段，不调相机、目标/阈值或跳过拒绝。
- 测试及验证器自身出现新的非预期故障，保留原始log后先开窄Astra轮。正式原件只读，不触碰数据库/claim；用户后续独立授权的正式运行属于另案。

完成是七个分配工况的事实记录和可审核独立读回，或按前提记录未执行。原组保持UNKNOWN＋8 NOT_RUN，B0、正式G1/G2/G3/G4与实机均继续根据各自原规则验收。

## 核对输入

| 路径 | SHA256 |
| --- | --- |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/plan.json` | `d0c577770ea9d464a017ae24d44b913b3d3685f179b6eb3fcebb044c4576d9fc` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/allocation.public.json` | `617c6dae6ca503cecc676d32f5da2f4fb4565c0c2cd298c2d45529cdf20245b7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/perception.public.json` | `87c5edefe0c57ace3182f7bb1e222ecff81a109d7e66c7ac5d3bdc7ea87b199c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase7-20261123/step-report.public.md` | `812a829e4f1658b621843a96c8efcd2905ef10cfc1b0912749fe1d3b06e5b1f4` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase7-20261123/vision.public.json` | `08ac6b27227c3c7b88a21b91697b171c2468fb1db88b6eeac500373058f08ab2` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase6-20261122/stage-summary.public.md` | `1f155213d785a1f79adba5beee4c1835e6dae65669a46fe362f6e1981a885961` |
| `scripts/verify_rgbd_physical_skills.py` | `993439e7b7636743911d9d5cf3fe3c3adf9d6bed3dbf3743599cfffc93095e6d` |
| `tests/test_rgbd_physical_skills.py` | `83752e289c6c6156c1952511d949c3e2f067d3f1bac4ca69a971a31716e74b57` |
| `src/cloud_edge_robot_arm/simulation/config.py` | `ece5dba5a710f63ba46bc99260ae768cec07c2773e7e0687bd2f55a4758f1d7b` |
| `src/cloud_edge_robot_arm/simulation/models.py` | `2199dacce74d62ae8d434110eef466d0136898005c9559581568873f74d7606e` |
| `src/cloud_edge_robot_arm/simulation/mujoco/backend.py` | `4d6dd9e0b92efab1b3895aa66473cb739e46558b3b47260caeec114a638f7bf4` |
| `src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py` | `fb2b5179d76cdc438c67f6447e450b495eba569bfbfefad4d38bb299ff82820c` |
| `src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py` | `9f1179a16aa3ef035c5eb452a900ff221050105455d058c2e3316d664f70307b` |
| `src/cloud_edge_robot_arm/simulation/mujoco/camera.py` | `a55c80e80ee469c6956274675fe48d684b43563c7f9bd4c85d5b45077ae5c107` |
| `src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py` | `a0b5891a70752400dcf0dea0cbe837476114148000b9eb345c27fe468860af50` |
| `src/cloud_edge_robot_arm/research/native_full_horizon_originals.py` | `408502ad0f4cd59dcd3d348a6d1642f2c13a7779df68371dc86e42de74179528` |
| `src/cloud_edge_robot_arm/research/native_collection_grounding.py` | `720a999f2e7b349eca2adad055fd69eb31e634c013aa8dee3cf4c208ac188204` |
| `src/cloud_edge_robot_arm/vision/pose_markers.py` | `acd89f0044fa7df44c1384692eef55c61d6280377a36e20e2649336669dff139` |
| `src/cloud_edge_robot_arm/vision/observations.py` | `ba4084710e44ad6dfa4b1e94ab94a3e645e09839f600f5bc18628acb23fb60fc` |
| `scripts/graduation/perception_io.py` | `d27f404c0cf66c9996bbf0cc4f4636575f47f96150847fa8a396127ddeda0f99` |
| `scripts/graduation/perception_capture.py` | `d30d3010103b5b94559984f861ba3a167b3b86c40e71a8ab4dcf4ea48c9682f2` |
| `scripts/graduation/perception_pixels.py` | `66fc067f423d02271526f6d184c8e245e85ec8c965fd914c73c64a423acd1999` |
| `scripts/graduation/perception_score.py` | `9675c7e4ef3ba74bcef21187ed8e101c682484a0de91a539509340dfd71fe819` |
| `assets/robots/franka_panda/scene.xml` | `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2` |
| `assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml` | `1e95054dc74e1c8ff51042290450b5e01e7410dd653870c553f056892efca140` |
| `docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md` | `dae788ab850288de1a524de37e21391e1e026b62375eaf06c798b8c87d49e0c1` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/AGENTS.md` | `afa2f8c3211c5f294c4e9c117bc8ee76506e10087160627100bc11b2c396beec` |
| `src/cloud_edge_robot_arm/vision/execution.py` | `69f2c1b7dabc0106697eb656bff67da331d4b5386433ae62b9f4f9ff094189f0` |
| `src/cloud_edge_robot_arm/vision/top_grasp.py` | `4726f87207d271dfad133852677a50abdc9b267b7a8688742cc87c6869dbc0ae` |
| `src/cloud_edge_robot_arm/edge/evidence/conditions.py` | `9583d8330ead52c68632c5ed63e8fb302044ca5b0ccbd8c5b5bf9cd064cbdddc` |
| `src/cloud_edge_robot_arm/edge/safety/shield.py` | `e2afac8c9f2e06270b9975562842d56177d2aa9ed05b833f0126f64951156cf9` |
| `src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py` | `71218ee666b8b90772cc9e3a03bab93c45c57d3ae6017c8ec734e9dd3fb13ff8` |
| `tests/test_visual_servo_control.py` | `6dda4a6cf64587008aca9ca102c73acc0bff3a6fbff34d4fffbb2828548b6bbc` |
| `tests/test_native_collection_stop_e2e.py` | `47cede684ba03cac6891605f71eda5576ba24206fc8b66301a232be8e7ab5c6d` |
| `src/cloud_edge_robot_arm/research/native_collection_application.py` | `f878b74e43f1315df3fdf6385c0d7199fe4e7ca1cd60776ccf2c413e1e61bfb5` |
