# 动态视觉开发源目录绑定补轮实施计划

gpt-6.2-astra / 2026-11-23 / 6416a6cc4b1b087c17cf1c738b202e8f28421e2a

首次动态开发allocate在EGL预检后、源清单解析时失败，联合登记尚未签发。发生物理运行0、动作0，原六个canonical工况和一个开发视觉实例尚待实施。

## 原始失败、来源与根因

- 保存的allocate.log SHA d7650569ab9b134e5bd6de9922d0e403f973a9ac63e0684d68aee60712ac6255，堆栈由dynamic_vision.inventory经source_inventory/_source_inventory_at进入_collection_policy，ValueError: registered schema/family pair required。
- 真实只读调用在最终候选工作树逐项重算SHA：SIDE_PREPARE_ONLY_FAMILY=side_y_plus_id7_75mm_r593，schema未指定(None)与显式native.calibration.operational.v4同一456项路径及SHA。产品digest使用UTF8、sort_keys、紧凑分隔，结果01f29ebf95837973d52c112d183e11a7abc361a750e42606f1811fad7c9ad04b；当前开发脚本digest使用sorted JSON默认分隔，结果f80d22e50fa46a1c294ddbfd65ce6d4aad04bc0f61e665340d670d80bf8eee38。
- r593 v4选择configs/research/native_operational_calibration_side_y_plus_75mm_r593.yaml（源码锁定文件SHA fa876ce35780fbf98f50aa493199b8e9020b347cd57575fe71ca3a06c117f4c7）。同一family显式v5合法但选择r595单教师配置，456项的产品digest为c8f48579e8ad7d3ce6efe5cf2b5bee3c96894ec69545997374c65fe6f3f7c519；v10组合确实拒绝。产品_registered_grounding_protocol通过显式v4生成当前准备源。

将上层教师协议封套native.calibration.operational.v10当作r593底层源枚举策略参数。其作用域不同；允许的默认v4和专用v5具有不同来源，错误并非EGL、资产或权限失败。

## 步骤与验证

### 1 修正开发调用

- [ ] 只改scripts/graduation/dynamic_vision.py、tests/test_graduation_dynamic_vision.py及本轮证据。去掉误用的教师v10常量，清楚传显式native.calibration.operational.v4。测试先以当前inventory()复现预期RED；实跑产品source_inventory而非mock，检查None和v4逐项相等，456项包含r593配置与注册资产；v5选不同配置；同一家庭＋v10必须保留原拒绝。禁止扩大产品白名单或重新解释v5。

### 2 来源归档与签发

- [ ] 用私有只读归档保存完整{相对路径:sha256}并独立枚举磁盘重算文件字节/集合，普通文件、无词法符号链接。公开登记注明family、v4、条数、紧凑产品摘要与原开发摘要各自编码、私有清单实际文件SHA并复核，区分内容摘要和文件摘要。冻结几何资产1e95054dc74e1c8ff51042290450b5e01e7410dd653870c553f056892efca140、原物理分配SHA、开发脚本/读回/测试最终SHA、父计划及本补轮两文件SHA。原六项分配保留；双方都就绪后才写新的独占联合登记，记录七个ID、一次/ID、各分配文件SHA与源代，确认无instance及无先前尝试。双方先核联合票据再启动，分开私有输出目录。

### 3 软件适配复核

- [ ] 在不获取正式claim、不运行预分配动作条件下，检查真实API签名与binding数据模型，包括Owner真实临时SQLite租约/attempt，build_collection_contract_v2的assignment/owner/协议步时基，validate_registration_handoff的原始/新鲜两帧、同一物理步、同owner，bootstrap_registered_collection_tracker_v2的完整catalog、registered_collection_step_v2返回元组/输入、registered_expected_conditions_v2和evaluate_registered_conditions_v2、Shield上下文与pre/post、实际SkillExecutor/VisualServo回调签名。能用原已封存开发RGB-D/软件夹具作无派发真实性状测试时复用，身份/时间不足的场合用显式隔离软件用例，不伪装成新运行。核实捕获的非预期Python错误在读回中与真实PRE/控制拒绝分列。新增独立类型或语义故障尚未在此轮实证时，保留日志并先另开Astra，不放松条件。

- [ ] 附加时钟预检：两份MJCF声明0.0041666667，后端initialize执行model.opt.timestep=config.physics_dt_s。canonical采用默认0.0041666667，r593开发视觉run显式1/240；二者在6000步的理想累计差约2e-7s。各自登记XML、config及实际生效dt。在隔离软件序列以各自时钟长至至少6000步，正控验正确源/步/时刻，负控互换时钟、错步号/时间时原视觉读回仍拒绝。真实实例据绑定核对各自0..末步；不改评分器/通用容差、窗口步数、控制或超时。

### 4 验证与一次实际运行

- [ ] 零动作预检先跑动态视觉、物理专项及ruff，独立再算登记/源清单。EGL/空间与占用情况满足父计划时，对已签6+1逐一实际运行一次。开发实例可按原方案经真实重新采集/前置条件、有效期、SOURCE/Shield、控制反馈尽早停止；保存真实帧/候选、实际步、拒绝来源、未执行工况与读回结果。确认初始step0观测与120步settle后bootstrap/准入帧实际不同；二者各自记物理步，不得将120步后的目标冒称由step0推导。若原父计划要求报告step0候选，可对封存的真实reset帧独立推导并标明仅作只读对照；绝不复用过期帧作实际派发。新调度若改变父计划授权的正式身份/算法/预算，须另轮而不是就地改动。软件签名/源错配是适配失败；真实PRE或控制拒绝是有效的研究阴性证据。已启动实例即消耗一次，不补跑，不转借正式或canonical额度。

## 实际前置与验收边界

- 检查所列输入和当前工作树SHA，匹配父轮预算、真实依赖与相机，无原始正式输出写入；生产src、几何、门限、控制器和正式claim全部排除出修改范围。原SHA与本轮生成后新SHA均记录。
- 预期RED仅为原开发枚举schema传错、既定拒绝用例。所有软件绿不代表新实例运行通过；完整读回/真实阴性/未执行阶段分别记录。保留初始失败、命令、退出码、报告、父阶段汇总、按路径推送和远端SHA核验。

## 输入指纹

| 文件 | SHA256 |
| --- | --- |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/plan.md` | `0e7f20762677a0e4f52be44f4add46316efe3ff3a70aa34866ddf35b6c54f195` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/plan.json` | `566581347e15ab63ab58be0d78c0fca6b2a104044f29d0cf2601772d2cb95f8b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-dynamic-qualification-20261123/allocation-physics.public.json` | `f9a4e29a755a468e9787d57c58e6264f24d7f6f656955eda1e69e7087163937f` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/allocate.log` | `d7650569ab9b134e5bd6de9922d0e403f973a9ac63e0684d68aee60712ac6255` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/software-final.log` | `65753f75354bf9bdd5a43f6987ee8caa1ff289d69f8651f043d0ba77ed5b1c8a` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/local-verification/round-graduation-integration-20261123.5bGCKn9h/dynamic-vision/ruff-final.log` | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `scripts/graduation/dynamic_vision.py` | `b71dc75ff294a13a3f3fb9cd2f049fb6b6775e016fc8de7bd02ef4508d9ba2d0` |
| `scripts/graduation/dynamic_vision_score.py` | `8840134a3aef3591c2fe757b12203ec5685cea9a185620aeac3dc07fb88b48ef` |
| `scripts/graduation/dynamic_physics.py` | `b19be78a952b5d333d82e307751da576f9f98c6ed2e218074a46efefb86a2551` |
| `scripts/graduation/perception_io.py` | `d27f404c0cf66c9996bbf0cc4f4636575f47f96150847fa8a396127ddeda0f99` |
| `tests/test_graduation_dynamic_vision.py` | `d9253b5e14daf485d66647155f1408431181314c214aaacf54dcbedc147c6d20` |
| `tests/test_graduation_dynamic_physics.py` | `0d10934a160c10636bfe8047ffc31c98a9ba7778683ef03159ed4125a2a147d0` |
| `src/cloud_edge_robot_arm/research/native_calibration_collection.py` | `3d7afa09892220b4ce9bc0dc063e8bc9058687e662e2f4f062675b90800cc82b` |
| `src/cloud_edge_robot_arm/research/native_collection_grounding.py` | `720a999f2e7b349eca2adad055fd69eb31e634c013aa8dee3cf4c208ac188204` |
| `src/cloud_edge_robot_arm/research/sol_molmo_components.py` | `572c767dc594decc409fc7ccf041f1a91661877ec4ada4175940fbd949e0539f` |
| `src/cloud_edge_robot_arm/edge/evidence/conditions.py` | `9583d8330ead52c68632c5ed63e8fb302044ca5b0ccbd8c5b5bf9cd064cbdddc` |
| `src/cloud_edge_robot_arm/edge/safety/shield.py` | `e2afac8c9f2e06270b9975562842d56177d2aa9ed05b833f0126f64951156cf9` |
| `src/cloud_edge_robot_arm/vision/owner_registration.py` | `17ccc6ea0c6e3095e77a37880b4fcbc7448eef88ecf94813369e5daaff28a43a` |
| `src/cloud_edge_robot_arm/vision/worker_owner.py` | `8128f8253e82deef5fab75fe5d24e79cd896c5588b9548b5ea4afe563731a21c` |
| `src/cloud_edge_robot_arm/vision/servo.py` | `5532047540e1ae2871031a0df24e12fa533c52f2c355681d80858b6af6f297e2` |
| `src/cloud_edge_robot_arm/vision/marker_families.py` | `93fe11e893b3d9caeb0d891e60ad46d9c26ce13b0c88357b5e4751c389c317e1` |
| `configs/research/native_operational_calibration_side_y_plus_75mm_r593.yaml` | `fa876ce35780fbf98f50aa493199b8e9020b347cd57575fe71ca3a06c117f4c7` |
| `configs/research/native_operational_calibration_side_y_plus_single_teacher_r595.yaml` | `da7426ab451bf59e76c682d605e5b211c79395b73fbe127990c1e0a1e2cf53cd` |
| `configs/research/native_registered_single_teacher_p0_v10_20261121.yaml` | `2b893cbcd1b959703ceada3663433eebb975adbcf8278a522967f2ad12131cf8` |
| `assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml` | `1e95054dc74e1c8ff51042290450b5e01e7410dd653870c553f056892efca140` |
| `src/cloud_edge_robot_arm/simulation/config.py` | `ece5dba5a710f63ba46bc99260ae768cec07c2773e7e0687bd2f55a4758f1d7b` |
| `src/cloud_edge_robot_arm/simulation/mujoco/backend.py` | `4d6dd9e0b92efab1b3895aa66473cb739e46558b3b47260caeec114a638f7bf4` |
| `assets/robots/franka_panda/scene.xml` | `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2` |
| `scripts/verify_rgbd_physical_skills.py` | `4129572bb3ff0d58312545bc3596c7d703e42f4673a6bc3dd013e0de3434a1f3` |
