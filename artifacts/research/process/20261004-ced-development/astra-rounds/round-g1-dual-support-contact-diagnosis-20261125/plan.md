# G1 双码支架横梁首碰的只读诊断计划

模型 `gpt-6.2-astra`，Git 基线 `8cf7c7afc3a9ee0aa85df3874b825d195b3092e3`，实跑构建 `5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212`。

## 实跑原件与安全结论

+30mm d02-02：MOVE_ABOVE 步896通过，APPROACH 步1228报 ROBOT_HARD_SAFETY_STOP。0..1228共1229物理状态，147张RGB-D。原始1227仅四个桌/方块接触点；1228仍有四个桌/方块点并新增三个左指/ID7横梁点，属于同一禁碰几何对、一个受影响步。整条原始轨迹中未记录右指/ID8载板接触；1221仅桌/方块。末条 accepted emergency_stop 在1228、序号227，safe_stop 成功。双盲像素与两份 score 的 SHA 各自相同，独立结果0/1、VIOLATION、零双指夹持；闭爪、抬升和释放均未运行。+15 d02旧失效发生1221于右指/ID8板，+30越过的是旧绝对步；两个动态轨迹的关节和物体状态须分别比较后才能陈述同姿态因果。保留这两次真实危险及所有此前开发尝试。 APPROACH视觉覆盖44/44，140个完整原生窗口P95 49.035ms、最大68.508ms；独立物理抬升0mm。已封存 d01 与四槽资格拒绝。

## 允许范围与独立还原

仅新增本专项目录下只读诊断脚本、结果、证据清单、步骤报告与阶段结论；私有图/数组写新独立目录，既有 XML、源、原件、运行账本不覆写。复核下表SHA、147图索引、分配/claim/episode/设备、独立盲读/score，对照+15原始score及contact_witness结果。用 f33d父及本轮归档各自的确切装配版本、原相机与真关节/指位/物体位置旋转，用原 restore/mj_forward 做静态重建，零积分/派发。封存FK/TCP/转角/物体复原残差、状态hash、两实体 geom 名/type/几何掩码和 signed separation。二个独立读取进程以同一组封存输入复核临界数值；若源状态无法复原或点面复算不一致，保留原始碰撞事实，将几何解释标为未证。

## 定位首碰与轨迹差异

对+30全1229步逐步按几何名称审阅所有非许可手/横梁、手/立柱、手/板以及允许/未授权其他接触并给出最小间隙及首步。对原图序列0138..0145（1168..1224每8步）与terminal 0146（1228）核对登记ID、在线决策和时间；1227/1228独立复原并记录当前相机重渲染，不捏造1227的原相机帧。分开比较+15运行的1220/1221右指–ID8板与+30 1220/1221/1227/1228左指–ID7梁；同一已有轨迹的冻结状态可交叉载入两套已登记装配，只记录离线反事实。分别列出右板/左梁在两条轨迹双方最小间隙、碰撞/未证分离、关节/指位和物体差异、最后允许运动及停止后的命令。对每个实际接触点记 MuJoCo contact.pos/frame/dist、两几何最近点、两体局部坐标与归属面（并列边/角、注明数值容差），以独立几何计算交叉核验。所有推导位置/法线明确标注来自冻结姿态重建。

## 固定根部横梁的可证明界

从生成器和编译 XML 两处核对：ID7梁沿物体+Y，+15与+30的Y区间分别[35,71]mm/[35,86]mm，X为[-4,4]mm、Z为[17,19]mm。检查这两个区间在世界/物体坐标与真实接触局部点的对应，区分根部/保留梁段/新增远端段。用3+3+9组 OBB 候选分离轴逐项记录有效/退化、符号间隙、最近点与是否真穿透（最近距离为0时区分刚好接触）。不能沿用以刚体平移板为前提的径向 δ 方程；梁的根端固定、中心和半长各增δ/2。若在被验证的1228固定姿态证实左指盒与现有梁实体有交集，则对仅外延、横截面与根部固定的同向长度参数，集合单调包含可证明延长不能消去该已有相交体积；不相交或在误差边界时记录可证上下界，禁止外推未观测轨迹。不得构建、推荐或运行第三个径向偏移。

## 下一个可检验思路及授权边界

现有权限足以做独立只读几何归因、原动态计分复核和束缚空间分析。可把两条既有轨迹各步的左右指/手盒变换到物体坐标，输出带原公差的已观测占用集合，并定位根部附着面与立柱连接面之间的禁穿区；只把离散采样视为已观测空间，若需连续扫掠结论须给插值运动/误差包络或标未知。由此形成待验证的结构假设：保留两块实体码与顶视的情况下，承力路径能否在夹指接近方向外连接方块与立柱。若单独获准重设计，才登记结构边界与载荷、真实接合面积和承力验证、材质密度/质量/惯量、碰撞壳与方块夹持面，先对冻结轨迹做独立稠密间隙/光学复核，再做新资质与真实完整动态验证；不凭密度/静态图像宣称结构额定载荷。改变横梁形状、根部、截面、走向或连接方式已属新支架设计，未在两种径向安装变更授权内。本轮不设计定型、不改模型或控制器、不新增硬件/仿真动作或正式研究登记。

## 验收与关闭

完成物理/视觉/命令/评分四条证据链，列出可证结论、不确定性和结构研究尚需的决定。保留两种登记径向装配的动态危险及性能改善事实，测试/反事实不计真实成功。+30 d01及此前+15 d01停止派发并列未运行；四个未使用摆放继续封存。真实历史完整成功仍为0，不启动任何新历史或正式/实机试次，不将安全停止作为抓放成功。完成专项报告后，独立结构设计和后续原生验证须另获授权并制定新Astra计划。

## 输入 SHA256

| 路径 | SHA256 |
|---|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-contact-20261125/plan.json` | `6a8eb89a5609a01dbbd5560c28a5379b95b72c7061522299185c7ced94fc3d9c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-contact-20261125/finger-plate-contact.public.json` | `2fe7b6500e8f91351335f8b2a44b5c766200d918bdecb8009d9d758eb0423ce8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-contact-20261125/contact_witness.py` | `7cff296e3d23d6405172ad9e2ba06b6824f9152a3a4e4790ad092bd427a9822b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-contact-20261125/static_screen.py` | `1cfb7d5d0584568a42d266d3a51aaf8b28c57e019231e621ca5c26506836e0df` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-contact-20261125/screen-clearance-summary.public.json` | `9dcf04781f98187d925d8067840a249355f9af3480b63aed619e70bfbf9c72bd` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-contact-20261125/screen-optical-summary.public.json` | `6b4f5992f104a216c87ab2b1df259119d9554f12d260845ee56be5319600e5cf` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-contact-20261125/screen-selection.public.json` | `4625888d3a356cbf7c856517240a3e1c37cadaa13ee27a6ff1c2ded59ae90178` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-capture-admission-20261125/plan.json` | `e8faaee12c3c781065ba5e9725355a74968a510a4515532027f400eea577e071` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-capture-admission-20261125/d02-outcome.public.json` | `89fbdf71f4420a6c91db9fa2386cc6aec7a3b69f46d4ea7ca2ebd3ea932ba583` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-capture-admission-20261125/d02-native.public.json` | `eb6b42fb3cdc85d19a7bea352cb3d223ff0acb44a0346218ce4abc6021057e70` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/allocation.json` | `acd61f9d29a44192963b1a42d637f5af44e6428220eab3bbde7a74eb7390fd51` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/allocation.json` | `6684994cec3ce193dc8be511adf417e7f8f515f28e7ee6084a282ac2ede757cf` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/attempt.json` | `d0fe6d602bd27eaa4bf25c3fa06e2b77bd985de2fab466fa06b5e846cd00be92` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/gate.json` | `4625888d3a356cbf7c856517240a3e1c37cadaa13ee27a6ff1c2ded59ae90178` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/source-inventory.json` | `643272775723504533b27a6a6443c8624bca8f609d6c60c87af09bd90ec0868d` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/acquisition.json` | `dae0b4ff5130fceb8226ed0c2fef672321668c126bbdbc0c25ec026fd55cf02b` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/score.json` | `5ccb4bc68d14dd3470783f4d8258221562d50b5554bcfd7423ea350f6ba3703c` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/scoring/score-one.json` | `84ba18c38e6d4c8b9878ee7d271aab16b998c0aafcaba2982f9175d10dbd4dd0` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/scoring/score-two.json` | `84ba18c38e6d4c8b9878ee7d271aab16b998c0aafcaba2982f9175d10dbd4dd0` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/scoring/blind-one/seal.json` | `cb7138c4b749ad319839e8263e096b10d18c58e099119b994d70227c5b3640dc` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/scoring/blind-two/seal.json` | `cb7138c4b749ad319839e8263e096b10d18c58e099119b994d70227c5b3640dc` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/receipt.json` | `7acf669e7ebf67f89570c8a1733f8870b12f33f676c4ec78f93ce9e1b947ff9a` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/run.json` | `25f4f24cb594ed56351807c2f1822f6207e5751f833e0c397261b72f11deabe9` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/offline-truth.json` | `f53da7fd5dec6282f6b3decd648afb2fcf2bc1131f2130ab037b0620f0cb7daf` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/online-audit.json` | `0d66e7e4a65910e65f4c8c4fc4194d02e0ff8ee08be71604029c0c1110ae5078` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/online-vision.json` | `23bc011cd7ecdfe65d9fb17d2dffc0a9a89202305b0ebea7130c168473c46417` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/backend-commands.json` | `6dea1a3740d0c1275a21c658895fca984774d36d3fec21f4a99ca927b9f8d2c0` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/pixel-index.json` | `c927076b8e66c6efa5e128773160ed8a1f7f619562c14a5d9484351e96c9f793` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/acquisition-seal.json` | `8149db7f065abc17f398eb7123e9f6f6766993b86c027746df90594364de8bd0` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/reset-observed.json` | `a726dca9fd9dcdc53040945dd3a16bb8769bf1deefe1197884e403b7913252be` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/assembly-reset.json` | `56743c84047afe31a5d84d13c669079670f954f498db0ead0236c8d342d3a3e8` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/frames/0138.json` | `5d54d882e6f00497b0cad7499efe914f8e6c0d553e0195c63609e4e253021b65` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/frames/0139.json` | `7ac80622242a8da4000ab9251adb62d6b74c6114ffa01ed6ede83c0acbbc0992` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/frames/0140.json` | `f2fd6e7e4a986a901eed4273945c971c63da14e3e01c04171d5cb9e49cd358be` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/frames/0141.json` | `0fca70a621e5e4a0131cb268a6dcc7caafa1e6604e72b9388e3b1bbb996118ac` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/frames/0142.json` | `a80a467c92194eae4559c02588eed43e1a1df044a7be6a3eb9f67a438f05b94f` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/frames/0143.json` | `454b851dab642ca38b84f86e6c40489b0c651d24d269c6e131205a9951a991ae` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/frames/0144.json` | `d8ad515ae23852a2238b1a42fdcf5697f416abfc5e2d14c56e78ac09936eed08` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/frames/0145.json` | `a889f703b1bc4a4de232634746598b5c4623fbd77870353f9a9db65e4b9a9895` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial30-contact-d02-02/d02/instance/frames/0146.json` | `0287abe37d3720b320d1bbb90b68f7e71a50461467daebc1ead2b3c40de2f829` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/score.json` | `bf95200107222fd8587128b0524e5d5997eaca871b51ced0e1b7a5444fc512ed` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/receipt.json` | `5b099a0c18f1aa602800fef190d05945c31ea42d15264af5e0bc0b7c2a54843f` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/run.json` | `bb7ee346faed8e53e786a473802423ce57518284d92b75c955228b8ae047358e` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/offline-truth.json` | `92d1115feb5a1367efeb08f945f7e678b40eb349064490488b39b63586d791b1` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/pixel-index.json` | `e71b9dfa1e5386cc1682c630a9eaf2b557211389abd074f1a27d69df37296da3` |
| `assets/robots/franka_panda/scene_g1_development_dual_id7_y100_id8_x100_low_bracket_v2.xml` | `a0bf24bdf2c7142e9aaeebdaf5dec02255bf06885dde0e2e56f009aaf89f9803` |
| `assets/robots/franka_panda/scene_g1_development_dual_id7_y115_id8_x115_low_bracket_v3.xml` | `47aae36ececab0d6bedd055a976fd74ce895e85a9827e1d0689afa6e3c3f8715` |
| `assets/robots/franka_panda/scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml` | `14a1a9fc2d2993fa28fbb873e25d1e9672c07b7433b3cb9ad27f07434c75efbe` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212/runtime-source/runtime-build.json` | `5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212/preflight.json` | `1a84ed4bf7a1b8f245afb2fb6fca4639cf827849285b4bd730aa7fa4f16c4589` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212/runtime-source/scripts/graduation/g1_visibility_radial.py` | `556d02bae81449295a221183712741debb16985a1995f0eb98593e0fef01c855` |
| `scripts/graduation/g1_visibility_radial_screen.py` | `80121e430d643efdaf05cbbec90bd1bf3deaacead970a682a9d5fa4fcd08b32a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial30-capture-admission-20261125/held-slots.public.json` | `dd26b072e7a6b55154a1d6d99879759c1517abc0e02f303fe5517a96ab8d30f1` |
