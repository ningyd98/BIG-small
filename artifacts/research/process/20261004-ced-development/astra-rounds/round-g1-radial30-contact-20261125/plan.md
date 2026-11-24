# G1 径向30毫米装配接触复核与开发运行计划

制定模型 `gpt-6.2-astra`，Git 基线 `3e4cffd3eaa3951a61bef46c07d75dcb91a2c4f0`，已验证的父运行构建 `f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892`。

## 触发与冻结

+15mm 已完成原生双门和4类/11项预检；唯一 train-radial15-timing-01/d02 使用本表批分配和独立单槽分配。真实139个窗口 P95 52.379ms、最大58.019ms，旧关口1088为54.903ms，随后 APPROACH 在1221触发 ROBOT_HARD_SAFETY_STOP。1220四个桌/方块接触点，1221两个桌/方块点与两个 right_finger_geom↔g1_dual_id8_plate 点。独立双读评分为 VIOLATION、0/1，1222步样本、146个RGB-D包、零双指夹持/零抬升，未进入闭爪，safe_stop 成功。保留原库/成绩，暂停既定的+15 d01单槽且记未运行。只启用之前登记的同向双板+30mm（中心130mm）备选，历史裸板和+15原件只读。

## 碰撞重建及稠密筛查

在新的专项目录，沿 g1_visibility_radial_screen.restore/dense_case 和原相机重建，先分别以历史源各自的 XML/真实关节、指位、自由体位姿/旋转、状态/时刻和 mj_forward 重放原碰撞，禁止积分以编造状态。逐步对照实际配对/多重数，重点封存1220→1221的每个 contact.pos、contact.frame 法向、带符号距离、两体表面最近点与 MuJoCo geom_id/name。转入双方局部坐标，依盒半径认定接近的±X/Y/Z面或边/角；边界或重建误差不唯一时写多面/不确定。复核稠密几何/原命令/硬停止顺序，不把数据中未存的实测接触点冒充原始观测。对 +30 在相同状态做稠密零步反事实：旧 d01至1120、旧 d02至1088共2210态，加新 d02的0..1221共1222态，总计3432 个按轨迹区分的状态，完整检查手指/掌臂与两板、横梁/立柱、台面、物体和目标区；核验各对最小带符号间隙、步、两侧/无遮挡原接触。沿原授权接触规则，未授权接触为零、复位无穿透；未证分离不放行。

## 定量停止界线

如果+30仍接触，报告全轨迹最小有符号间隙、原API读数、接触点/法向、实体及最差时步。右指与ID8板均为盒形：固定失败姿态，以原15条盒分离轴（剔除退化轴）的投影区间，令板中心仅沿登记的局部径向移动 δ，解出该对每轴重叠的 δ 区间并求交；报告从当前点至首次严格分离的位移下界/区间、数值公差与是哪条轴。用原几何/距离独立复核，区分仅切触和严格正净距；涉及其他相连件或多步时须联合检查，把能证明的局部界与全系统需要量分列，限制适用姿态。如果方向无有限受证分离、形体不支持定量或恢复误差过大则列不可判定。仅解析固定姿态，不生成、试跑或推荐第三种装配。两预登记改型都不足时封存并停止机械路线。

## 光学/物性与最小实现

+30 XML SHA 14a1a9fc2d2993fa28fbb873e25d1e9672c07b7433b3cb9ad27f07434c75efbe。编译复核ID7沿+Y、ID8沿+X，两中心均130mm的板、静区、全部字格及连接面；同原相机/码向/尺寸/材质密度，用候选真实质量、惯性、COM、contact flags和 reset 实读登记。以锁定的 f33d25e2 实际 grid/vision 重渲染原22光学锚点，再加新轨迹最近8帧反馈（步1160..1216，每8步）及1221 terminal，共31个按轨迹与帧标识的锚点。分别保存原15、正常30和沿原匹配深度噪声方案的新图/相机/注册，逐项核对应有当前实测标记、唯一性、10mm误差与双码冲突、单码/全遮挡拒绝等原门槛。原始包只按原装配和 SHA 解读，新的合格率明确为改板重渲染。准入必须同时有独立稠密和光学资格。

## 构建、登记、评分和新资格

在开发专用构建/装配选择、资格和评分适配器及其测试中，增加明确的130mm分支，从实际通过门槛的 f33d25e2 父源逐文件核验，只替换已登记的 +30 XML、asset/family/registration标识、object_T_marker、源锁、质量/惯性、必要的开发构建派发与静态证据绑定；v2检测源/软件发布与预算仅在 SHA 逐项一致时作为父软件证据。原 +15 eligibility/score 不得用作 +30 资格。旧模板标识先验旧父再验新派生，不移除旧保护。盲评分按130mm独立注册重建刚体和两码抓取点，独立验证0.100/0.115/0.130m区分，保留1e-10核验、10mm分歧和原物理评分。开发 CLI 的 prepare→preflight→issue 同一新 generation；用原历史资格姿态及 seed 正常复位，真实顶视4类/11负控，单码双码当前 owner/servo/target、全遮挡保护、零运动/零物理步，两个独立像素读回、+30 稠密/光学报告和源码/实体摘要全部绑定。原控制器、手/板碰撞、抓取守卫、100ms及物理评分冻结。

## 唯一开发槽、验收与停止

在旧919原件/账本、源锁、单EGL/原解释器/相机 f33940579c533afe 和16GiB核验后，只有+30稠密、光学、软件/独立评分和新代真实零步均过才开展训练。预登记 train-radial30-contact-d02-01 只含d02，先用正常 native capture/audit/双读/join/score 完成全部原意图；另一个标签 train-radial30-contact-d01-01 只含d01，验证旧1120左指板问题，各至多一次且保留全部结果。d02任何危险接触、安全/完整性异常立即停止，d01标未运行；新原因另报 Astra，禁止靠复试取代原失败。d01如发生危险也停止；未到历史危险区就按实际标未知，独立报告，不外推。动态验收沿主计划真实八动作、合法双指夹方块、≥50mm抬升保持≥0.5s、释放区≥1s、全程零违规、误放行零及规定覆盖/误差。当前完整物理成功为0；只有获得至少一次独立完整安全物理成功且已要求的危险核验和冻结条件满足，才冻结该代并按主计划签发四个从未使用的新摆放各一次。软件/反事实/历史开发/四槽/正式/实机分开。无新正式、实机和任务模型。

## 输入 SHA256

| 工作树相对路径 | SHA256 |
|---|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-fit-reuse-20261125/plan.json` | `70d6f895fa88b80d0e5b2415c5cb51b63f39f17abe53252da2eb782be5535c5f` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-fit-reuse-20261125/d02-outcome.public.json` | `e4ff9e88f258ad176a3e14469fad68027736cb66a5a401d8b76a0e6c6ec1e9f5` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-fit-reuse-20261125/d02-native.public.json` | `de582c491760692d172996723451a7512f42ec8b3899bfa0fc28a896b649f5a8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-fit-reuse-20261125/replay-release.public.json` | `81bf8af00c237912b963b73263041ed7340ed2f921bba5545fa59213f0586ea8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-fit-reuse-20261125/paired-budget.public.json` | `861599926e5cc428609e207fa0389a7bfd8aff67778dff4d850833cbd52b607f` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/plan.json` | `f73a383f23408f6d53d30677928545ed4e515419ab0ed16da7b391c1275ed015` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/assembly.public.json` | `c5fcdcf05cbffc6d527bd2c3e538a6be41f5415094e900c9174ff34dad7ec140` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-selection.public.json` | `509b79dacf796a20038b510c49a7204f6260614a13335d04186faa0941eb2511` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-clearance-15-summary.public.json` | `8286ea088e119ae70b17d500d20b71932480ae42a23b0fffe005e14cf7d24903` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-clearance-15.public.json.gz` | `73ab945d884f58327e4a1c1859661d9fefde4df0dc2a9f40ffdf6502be5ec826` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-optical-15-summary.public.json` | `3dd4cfd9ebd4624af37f1e6033d05afa6a8955d5ba462ce7aeb9e19557cf3be1` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-optical-15.public.json.gz` | `87150ea9f7479cc7a61bf27454438007f1b0515f80e8e519ce4af2c5b32458d0` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/allocation.json` | `eefd578cb93651b7ed3bc2a8f2690ecb5d031e5fd0c48f95ff4350538c437a97` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/source-inventory.json` | `672a0e87d3c147ea65e4e7d290bd230b1ff4884f3b30949dea7e677016c92faf` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/allocation.json` | `b86988ebcc49dc379c5c42fb0041d4471bf3336991ac3426e53602e1a6805e9f` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/attempt.json` | `7c5aaaee6bc52f5f4b5f1f9be6eabdcdd51ad66f06cf5cc32c874ae307e4b538` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/acquisition.json` | `c1de3483316ce8b2e2db723b3067d76d0e3fffe03998c8c74ad3e8c45b63ed52` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/score.json` | `bf95200107222fd8587128b0524e5d5997eaca871b51ced0e1b7a5444fc512ed` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/run.json` | `bb7ee346faed8e53e786a473802423ce57518284d92b75c955228b8ae047358e` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/receipt.json` | `5b099a0c18f1aa602800fef190d05945c31ea42d15264af5e0bc0b7c2a54843f` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/offline-truth.json` | `92d1115feb5a1367efeb08f945f7e678b40eb349064490488b39b63586d791b1` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/online-audit.json` | `bb8055acbf4a9cbd0375d30483eea47aa6e4d4c1ca0c69c744ca7686b2fd811d` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/online-vision.json` | `a7556f519133bd1f31be348ea365e38a03cde101cbd932729b00d18c7a18c811` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/pixel-index.json` | `e71b9dfa1e5386cc1682c630a9eaf2b557211389abd074f1a27d69df37296da3` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/backend-commands.json` | `3d0b504dd2dd81d77ff7b28f3c2a486b4542667fadd0a65d454af2c372621754` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/acquisition-seal.json` | `8a6db765b45dd333875e5e2a23309d3c7ab2aadd9a3325feea599dfdfca5dd8d` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/assembly-reset.json` | `fb3f47be2a74e3199373d2c53d6dd814af0070d0807542f0edea16908a9a217e` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/frames/0137.json` | `ec3db25c0660dc5873abcb8d9e2f96cc9c9d50ab53cd2cad74b2772848cbbf8d` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/frames/0138.json` | `347f4c75b4cdaf92a066d6aa2addd4ec63f67a9b5e01adc38aa43e90aae3ec68` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/frames/0139.json` | `b67a453d004676a1ed066492daa1d164f771d3bf5c2ce8caad8f8453df5c25f1` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/frames/0140.json` | `4d157427e87fa794a0723f6532d592b10932b661357a4950b7f6d45c90e3bda0` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/frames/0141.json` | `3bb1c0aacc797039156a9a7071b37565bfc08ae8988ca671cd1599519f9892c0` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/frames/0142.json` | `65642d311aa9dfd569d7ed567b07adf89a750cb80e19db85e8afd29c43c3696d` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/frames/0143.json` | `aff3fa72464c719eccab74e2b42fc04e95faf983f75016b690597d101949f27e` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/frames/0144.json` | `edfc9b34af001a8f8ae0bc16e464fc4344f868ab8b79305b5bf2ac505b917319` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-timing-01/d02/instance/frames/0145.json` | `930bf87facf857e46e7b231b5e8c99de36f584fb6546a4ab452d24ff6f1330af` |
| `../../local-verification/g1-first-refusal-dual-20261124.mynavkg6/trials/d01-dual/instance/offline-truth.json` | `492ff411ccde510d7cbfb56fb88e2ad2908a92e11ee903d41e9a7fbc3c22ffa9` |
| `../../local-verification/g1-first-refusal-dual-20261124.mynavkg6/trials/d01-dual/instance/run.json` | `df318210795b7fe24b36e066e624c60eaefada375f92c4376fa4af7d420d0d85` |
| `../../local-verification/g1-first-refusal-dual-20261124.mynavkg6/trials/d01-dual/instance/pixel-index.json` | `0d6c9596cbd182293d5e32e9d8c9fd89da85a05436a4c8e8743551cca1a606d1` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-feedback-deadline-01/d02/instance/offline-truth.json` | `15bf5e97436abf0483f3f6d5919b61376a6ce778669d7c0856875e5d9d9de7c9` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-feedback-deadline-01/d02/instance/run.json` | `f3f805c347acda19fb3dbc658206d128187d8470c089d3c7a6e1680d8202ec00` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-feedback-deadline-01/d02/instance/pixel-index.json` | `d853d9bb680b6fda24b508cf1f4b728a95840445691792eee39157b96828a65a` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/runtime-source/runtime-build.json` | `f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/preflight.json` | `8e12a9e9ab1417c43d9ed5a2f98f30ee41f572225838f1bfbaa55073d7bebe01` |
| `assets/robots/franka_panda/scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml` | `14a1a9fc2d2993fa28fbb873e25d1e9672c07b7433b3cb9ad27f07434c75efbe` |
| `scripts/graduation/g1_visibility_radial_screen.py` | `80121e430d643efdaf05cbbec90bd1bf3deaacead970a682a9d5fa4fcd08b32a` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/runtime-source/scripts/graduation/g1_visibility_radial.py` | `556d02bae81449295a221183712741debb16985a1995f0eb98593e0fef01c855` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/runtime-source/scripts/graduation/g1_visibility_mount_runtime.py` | `e7b49690ae4e079c6f52b44e144c32ccfb9e7d635cbff2aa092e7cd9eefce2ed` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/runtime-source/scripts/graduation/g1_visibility_runtime.py` | `01943ed07fa77ce778caf43f8237d25954615b21f81ecf4c43129ce74a1f6bd3` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/runtime-source/scripts/graduation/g1_visibility_trials.py` | `ef5978a7d69e68a84c549126302f92af3d1f3092d073c64b1cfccb76e7af098e` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/runtime-source/scripts/graduation/g1_visibility_grid.py` | `cefc238814296daa8c33d2a42c7e4844452391f5e910ef1ab324c56de4add088` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/runtime-source/scripts/graduation/g1_visibility_vision.py` | `2e98bd0d96e4b8aa58a58b0ef1d959a8b3fde259f3ae7b948eb68ce4ffa6a169` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/runtime-source/scripts/graduation/g1_dual_pixel_readback.py` | `93c82f96233e480bef041fee1655401d20ed7ffb0dc1e3442c26e30f34af238e` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892/runtime-source/scripts/graduation/g1_dual_batch_score.py` | `24384ffc6df1423d76a2f4b3d4a93e73c485d87c4d90ffc433a07ad4151c4e0c` |
| `scripts/graduation/g1_visibility_radial.py` | `556d02bae81449295a221183712741debb16985a1995f0eb98593e0fef01c855` |
| `scripts/graduation/g1_visibility_mount_runtime.py` | `e7b49690ae4e079c6f52b44e144c32ccfb9e7d635cbff2aa092e7cd9eefce2ed` |
| `scripts/graduation/g1_visibility_runtime.py` | `01943ed07fa77ce778caf43f8237d25954615b21f81ecf4c43129ce74a1f6bd3` |
| `scripts/graduation/g1_visibility_trials.py` | `ef5978a7d69e68a84c549126302f92af3d1f3092d073c64b1cfccb76e7af098e` |
