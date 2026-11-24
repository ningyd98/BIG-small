# G1 径向装配逐帧拟合复用与性能复验计划

模型 `gpt-6.2-astra`，Git 基线 `4d1374ba1ecea42eecb0b8aa72f926d15c67d5fa`。本轮以原生运行 `36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf` 为正式配对基线。

## 保留失败与固定对照

原生父36f9658b在 d02 步1088实测150.336ms 后停止，独立物理结果0/1。v1 grid c0e80c0b、vision 2e98bd0d 的离线 release 284c1497 可复核778历史、335开发、44静态和20控；其性能预算未过，未签发构建或历史作业。675个热配对估算 P95=81.795644ms、最大83.897579ms；615个顺序样本 P95=58.110254ms、最大83.003291ms，60个重点重复 P95=83.785646ms。不得重加权、改门槛、复测 v1 挑选通过样本。

## 最小方向与退出条件

仅在 g1_visibility_grid.py 及对应 grid 测试写第二版优化，先按实际 sealed c0e80c0b 输入锁定逐候选差分。1088 的已测瓶颈是弱网格精炼、连通片种子和重复邻域运算；记录计时方法/开销，未经 instrumentation 的配对值用于验收。_accept 的两组岛候选有42和22次完全相同索引的重复 nearby；以局部 ordered 数组与索引为键，在第一次筛 peers 时存未修改的精确 mask，正式消费同一索引直接复用，保留临界值标量回退与原先顺序。_seeds 每次复用同一采样的 BORDER/DATA 视图或提取结果；先做原字典精确匹配/对比，之后仅对幸存行执行原边框计数与偏差（例如2112、3456组中仅121、77组仍需检查），不改选中顺序/strength。可预计算与图像无关的字典齐次格、静态轴/索引/旋转单位阵；同一帧同 dtype/形状/字节的输入才复用其结果，不复制世界状态。

## 拟合进一步降耗

如前两项不足，在同一批 _weak_grid_cells 原四轮迭代内按精确的 design[fit] 矩阵字节、形状、类型、行顺序及 rcond/秩语义分组。1088 的主要 code8 第一轮61个右端仅9种矩阵，后三轮各61种矩阵；右端每轮均不同，禁止仅按矩阵复用解，也不能承诺后三轮有重复。可对完全相同矩阵用原 lstsq 多右端一次求解并保持秩/原顺序；近奇异、数值不一致、阈值附近或投影误差不能证明时沿原标量路径。优先用完全相同输入的原生运算/缓冲区复用；新QR解算不得用正规方程或舍入键取代原LAPACK秩判据。所有视觉/反射/外来/重复/冲突、格支持及0.13边距和4次精炼保持；禁止跨帧缓存观测或用真值/历史ROI。目标在相同1088帧相对于v1节省至少5ms，以一组固定交错微测展示成因和副作用；该数值是工程目标，实际派发只认冻结预算与等价门槛。 若合法矩阵之间几乎无重复，可在冻结 NumPy 2.5.3 中使用与原 np.linalg.lstsq 一致的 LAPACK gufunc 按有效行数分组、保留每个独立 A[fit]/b[fit,None] 逐系统运算；固定 dtype、signature、默认 rcond 解析、rank 和奇异值语义。逐系统验证 x/rank/s 及最终裁决精确相等；版本、API、shape 或数值无法准确复核时使用原函数。244个 A+rhs 无重复，因此不以整解散列为主方案。三组白岛6576候选中只有207行通过字典与对比，可精确缩小边框统计。 补充软件对照的516个真实拟合，分组解、rank、residuals、singular values 逐字节一致；终帧纯拟合中位3.504→1.843ms，单项只节省约1.661ms，5ms目标还依赖邻域复用及字典筛选，必须以完整像素和配对估算实测验证。

## 无循环依赖的两次计量

先固定 v2 grid 字节和不变 vision，独立封存候选文件清单/导入/依赖；计时与复算脚本以外部登记的候选清单为输入，不将它们自己的 SHA 或未来报告 SHA 嵌入待计时的 grid。第一类为逐帧像素 wall time：按原 pixel_timing.py 的123个反馈身份/122个物理步、5个独立进程、每轮123次顺序及指定1080/1088各30热邻居、另5个冷样本；保持同一环境、交错顺序及原控制/CPU配置。正式主对照必须用36f9658b冻结实际算法，v1仅作辅助瓶颈微测。第二类以完全相同的原生窗口及新第一类的已封存逐行时间、原帧 SHA/标签/原始方法，用原 native_window_budget.py 独立计算配对估算；原生原始值、像素实测、估算和冷样本分别发布。两项均无需预先生成含未来预算 SHA 的 runtime。真实100ms控制器结局只在随后真实作业给出。

## 发布与正常入口

在新轮目录用原规则双进程冷读，778历史/335开发/44静态及20控逐字段与36f9658b相等；核对阈值边界、近奇异矩阵、不同右端、重复候选、排序、切换帧/装配和逐 consumer证据。先封存测量、语义、源和原帧清单，后在新目录发布独立 release 及新 paired-budget。严格沿原已登记公式和检查：675热原始分组/全部子集照报，像素 P95≤35ms、最大≤45ms，原同帧窗口估算 P95≤80ms、最大≤90ms，保留5冷和所有失败。再把已生成的 release/budget 摘要绑定至开发 build/qualify/preflight/issue 的独立新轮分支；不得修改旧证据或把新数据填进旧 v1 分支，不允许传入任意外部 gate。已冻结候选的像素和语义代码不嵌入 runtime 自己未来的 build SHA；prepare 最后生成运行源锁与 generation。改变候选 detector 或测量方法后不得沿用旧 release/预算。新分支冻结原115mm装配、相机及旧父来源、注册和评分，旧 v1 入口必须仍因旧红预算拒绝；新增集成测试同时验证外代SHA/掉包拒绝及新代正常路径。

## 实际运行与停止

校验原919原件/账本、EGL独占、环境和16GiB可用，采用父36f9658b允许的受限 overlay，原生零步4类、11负控及独立评分绑定重新通过。沿上轮既定标签和原配对历史 d02、独立历史 d01 最大各一单槽作业，正常 capture/audit/双读/join/score，危险或完整性异常按上轮暂停。所有历史真实分母保留，d01用于检查旧已知碰板，不充作重试。仅在独立评分至少一例完整物理成功、零违规且冻结/登记条件满足后才按主计划四个未用摆放各一次。软件/静态/现场/正式分别报告。若原设计两类局部原语优化经实验证明无收益或影响任何歧义判定，应回退该变化；仅对最终锁定的 v2 做一次完整登记预算。若预算仍红、复现存在系统/安全/数据库层不可控下限或语义不等且无法用登记的原路径保持，记录热点余量/相同输入、明确本轮未放行并返 Astra。不得反复跑相同预算/历史槽寻找通过。

热点剖析脚本和报告已核验于基线提交 4d1374ba；检查这两个输入时从该 Git 树读取，后续补充剖析单独封存。

## 输入 SHA256

| 路径 | SHA256 |
|---|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/plan.json` | `567e992a68593aecb32e73a3c3cd5bd9dc4a73d2c8ef2adb5146b91abc944171` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/paired-budget.public.json` | `f0c4c6577de723af06c63a4b31d06423787a7f8241bea3576afcf9c7300d867c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/paired-window-rows.public.json.gz` | `0e8db57e83c7e6a8f2bd5e10781d40f28894827da2320702b8ab7846bac27ae3` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/pixel-timing-samples.public.json.gz` | `64a368217dcddf26e194793cd9220602471d525c4ad7e167855c24d42bb5c964` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/pixel-timing-summary.public.json` | `bdbdff3741a87cdd453462473f568086ae80c2700a977bebf35d6697ab5ce738` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/remaining-pixel-profile.public.json` | `d3049de516621aea1aeb123ccaf3ebfce68f4dec6105b1ecb24a168d88a28e91` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/pixel_residual_profile.py` | `ab57c66a6424a27483fd69dd1ba104c271e6df1533bb9153df7057b443bc3ba4` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/native_window_budget.py` | `6f1fc4c94dd77813e3910bf444b6a7b3509aa3078d3685f00ca23c09c2bc3ba8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/native-window-segments.public.json` | `99f99fad5f00d06ae6b446c75ce60646019a0da9e1640441ee87a1fe0098b2c5` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/pixel_timing.py` | `98b5c8dd78eb0e6cae01161c6013206d05ccaee22f491b928fe05868be6f04aa` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/semantic_release.py` | `52ec593c5eaccd1743cd847260b88cbdb7ad6eb349faf4b2a7c8fad8c50f11da` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/semantic_replay.py` | `de30105f06403236adb9fe0003bdd09e8dad8e064924c204f6052ff2cab1fdf7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/publish_software_gate.py` | `ba9b3fe9d58bc6af1f50b372daf9bb5cf6b51f158d05a990187ba16f88b35da7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/semantic-equivalence.public.json` | `cfa5f4460edfb3a9333845e116c623b1c801af8e589ddd36daf48944919a0cec` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/source-snapshot.public.json.gz` | `49e66201d1ae0f68abd840362010bf7998d4b0e8986742b480eb2fed1515330c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/semantics-inputs.public.json` | `14d585713198cf6b9505d42920a1f24dbae04c72749ab3c749409d7c264153ec` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/replay-release.public.json` | `284c149700f70b050fe92ddfc1d222fd105f229993becf0b8af1a78bc6cd2120` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/integration.public.json` | `d714219b4a441dd326a30303e8601b43255a012ac550c02f4cace66be97eb466` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/runtime-refusal.public.json` | `1c4b9a6bbf69679c5b366f77740a991d572bb8cca9595316fff3a1979c9552f7` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-01/score.json` | `9170614d1a63e2f331b27c19236f2d8ba70881f3fe3d5b0b61e2ec9bcced1645` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-01/d02/instance/run.json` | `d28568755e51d7d1a380837c2cc773bbaef37f8d6a4dab4fa4346ea876d7669f` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-01/d02/instance/online-audit.json` | `6a0c9d1b2ab9a59c8aa8077fd09e005279fb214b78f94c4c811e318a6c4992fa` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-01/d02/instance/pixel-index.json` | `ba04ebd17177dbaaaeea0f0fb5947e2c9bee56787335c0c65975fc4a5ca755a6` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-01/d02/instance/frames/0127.json` | `088b5c1a33351f3491dfa0e1a64d8f8e7b46dbd6bfe7abff29fe794602462fa1` |
| `experiments/results/g1-visibility-pose-repair-20261124/batches/train-radial15-01/d02/instance/frames/0128.json` | `93d2ceba270fcd109adace2d158483aa3aeea6217717fdb9428af5594a4ed501` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf/runtime-source/runtime-build.json` | `36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf` |
| `experiments/results/g1-visibility-pose-repair-20261124/builds/36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf/preflight.json` | `90a4c0ed2ab0370e426acefabfc8eb1f991139c7b9178e0c654cf31df6a7723a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-visibility-approach-geometry-20261125/screen-selection.public.json` | `509b79dacf796a20038b510c49a7204f6260614a13335d04186faa0941eb2511` |
| `scripts/graduation/g1_visibility_grid.py` | `c0e80c0b3b36ad397a4d26146e9dc8c6d2063669dd28244bb9beb29f6b211e69` |
| `scripts/graduation/g1_visibility_vision.py` | `2e98bd0d96e4b8aa58a58b0ef1d959a8b3fde259f3ae7b948eb68ce4ffa6a169` |
| `scripts/graduation/g1_visibility_runtime.py` | `ce7901c674969b83ff6e24f86d2de9b36b8dcae50d9be1326252ba160451d491` |
| `scripts/graduation/g1_visibility_mount_runtime.py` | `e7b49690ae4e079c6f52b44e144c32ccfb9e7d635cbff2aa092e7cd9eefce2ed` |
| `scripts/graduation/g1_visibility_trials.py` | `8331e52515e17cb168212515d6faf1cdb2e92bdab0e42946361bdedc50e38834` |
| `tests/test_graduation_g1_radial_native_grid.py` | `976af030e7c771f494d10d3e5955c2fd8e82d4286406848775349956a89fd105` |
| `tests/test_graduation_g1_radial_timing_runtime.py` | `5bd0df8b1f70dae98c56d29a0e0796d581f1ab53cce2c9ccf728196aebebfceb` |

补充剖析使用另一次局部软件对照，其文件版本如下。

| 路径 | SHA256 |
|---|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/remaining-pixel-profile.public.json` | `9c03feeb578a72ef0ac5129ece72ec61ec2fe1abab210bfb21047b27e2ad9b27` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-radial-native-timing-20261125/pixel_residual_profile.py` | `fa5b65eef9ed66e53b02246d8ec8f72e1e389c75df8c3ed717acb64c8140ea03` |
