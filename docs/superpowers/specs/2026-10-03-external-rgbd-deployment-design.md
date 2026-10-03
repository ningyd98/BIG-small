# 第三方真实 RGB-D 数据部署设计

用户已明确授权按以下范围连续实施；以粘贴的原始要求为验收标准。此工作扩展现有 datasets 命名空间，保留现有 RGBDObservation 的严格实时契约；缺失时间或标定的第三方数据使用可空字段的独立离线观察类型，禁止伪造必填实时标定。

你是 BIG-small 项目的数据工程负责人、机器人视觉工程师和测试负责人。请在当前已有仓库中实际部署两套真实 RGBD 数据，并完成可复现的数据读取、校验、索引和离线接入。不要从零重建项目，不要只给方案。

【目标与范围】

部署对象仅限：
A. RoboMIND：优先真实单臂 h5_franka_1rgb 子集。
B. GraspClutter6D：RGBD 场景、相机参数、官方划分，以及所选场景需要的位姿、分割和抓取标注。

交付闭环：
环境检查 → 来源与版本核验 → 下载计划 → 下载/续传
→ 安全解压 → RGBD 解码与质量检查 → 数据索引与划分
→ DataLoader → 离线预览/回放 → 项目接入 → 实际验收报告。

本轮不做大规模模型训练，不接通真实机械臂，不修改 PCSC/ETEAC/AUTO 的决策逻辑，不将离线回放宣称为闭环控制或 Sim2Real 验证。

一、先审查仓库与环境

1. 阅读 AGENTS.md、README、项目架构、数据/感知/仿真/实验模块及已有验收脚本；以当前代码为准，复用已有能力，不重新创建同类体系。

2. 检查 git status、当前分支、HEAD、未提交改动。保留用户改动；需要隔离时使用新分支或 worktree。不得 reset --hard、清理用户文件、直接推送或合并 main。

3. 检查操作系统、Python、依赖管理方式、CPU/内存、GPU、磁盘空间与 inode、目标目录权限、代理变量、官方源连通性。

4. 沿用现有依赖管理；必要时建隔离的数据工具环境，不升级或破坏现有 ROS 2、MoveIt、MuJoCo、Isaac、PyTorch/CUDA 环境。基础读取和验收必须能在 CPU 上运行。

5. 数据目录优先使用 BIGSMALL_DATA_ROOT；未设置时使用 $HOME/datasets/BIGsmall，并记录解析后的绝对路径。不得假设 /data、/mnt/data 或 NAS 已存在，不自动挂载其他存储。

6. 默认继续执行明确且可逆的步骤；仅将授权、容量、网络等真实阻塞记录为 BLOCKED，不因单个数据源受阻而停止其他模块实现。

二、官方来源与可追溯性

RoboMIND：
- https://www.modelscope.cn/datasets/X-Humanoid/RoboMIND
- https://huggingface.co/datasets/x-humanoid-robomind/RoboMIND
- https://github.com/x-humanoid-robomind/x-humanoid-robomind.github.io/blob/main/static/all_robot_h5_info.md
- 同一官方仓库中的版本说明、Quick_Start、语言指令与数据质量工具。

GraspClutter6D：
- https://huggingface.co/datasets/GraspClutter6D/GraspClutter6D
- https://sites.google.com/view/graspclutter6d/dataset
- https://github.com/SeungBack/graspclutter6dAPI

下载 SDK 参考：
- https://huggingface.co/docs/huggingface_hub/guides/download

要求：

1. 先获取官方文件树、文件大小、访问条件和 README，再确定精确文件清单；不得虚构文件名、可下载子集或相机参数。

2. HF 数据集锁定完整 commit SHA；魔搭记录可获得的不可变版本或版本标识、文件清单和摘要。不能只有 main/latest。

3. RoboMIND 在 HF 可能需要登录并接受访问条件。仅使用用户已授权的凭证；不得代填个人信息、代接受条款或规避访问控制。魔搭作为官方候选源，也必须独立核验其访问权限和版本。

4. 不把不同平台上的同名版本自动视为逐字节相同。不得混用不同来源的分卷；只有经过内容一致性检查才能复用文件。

5. 保存来源、版本、许可证、引用信息和获取日期；没有核验到的条款写明未知。数据与衍生样本不自动上传或公开发布。

6. Token 只从既有安全凭证或环境变量读取，禁止写进代码、命令历史、日志、报告或 Git。不得关闭 TLS 校验。

三、目录、预算和下载机制

数据目录与 Git 仓库分离，建议：

$BIGSMALL_DATA_ROOT/
  downloads/          # 原始压缩包或下载文件
  raw/robomind/       # 保留上游结构，只读使用
  raw/graspclutter6d/
  manifests/          # 来源、下载、校验与样本索引
  processed/          # 必要的派生数据，避免全量复制
  previews/           # 本地预览，默认不进 Git
  reports/
  cache/

新增可配置的默认预算：

- 本轮总新增下载上限：250 GiB。
- RoboMIND 首轮子集上限：10 GiB。
- 全流程至少保留目标文件系统 50 GiB 空闲空间。
- 下载并发默认 4，解码 worker 默认 2。
- 所有上限可配置。
- 本次允许在上述预算及磁盘门禁内下载 GraspClutter6D 的完整必要分卷，但不授权下载整个 RoboMIND 或购买额外服务。

必须实现：

1. plan/dry-run 先输出文件清单、待下载字节数、已有可复用文件、压缩包依赖、预计解压与缓存峰值、最终剩余空间；已超过预算时不得先下载再报错。

2. 解压量未知时不得声称容量足够。先争取获取 archive listing；无法预先取得时，可按压缩量的 3 倍加 50 GiB 作为启动门禁的保守估算，明确标记 ESTIMATED，后续以真实 listing 重算并持续监测。它不是保证足够的实际数据量。

3. 使用当前 SDK 支持的按文件下载、revision 固定、缓存与续传机制，不使用未核实的旧参数。不得无过滤地 snapshot_download 整个 RoboMIND。

4. 下载有有限重试、退避、超时和进度记录；保留续传状态，不因失败删除已验证文件。第二次运行跳过匹配清单的有效文件。

5. 避免 HF 缓存、下载目录和 raw 目录重复占用多份大文件。原始文件不改写；需要转换则写到 processed。

6. 流式计算本地 SHA256；上游有可验证摘要时进行比对。没有上游摘要时只报告“本地摘要已记录”，不能称为“已通过官方哈希校验”。

7. 解压前检查分卷完整性、条目路径、绝对路径、../、链接逃逸、预计展开大小；限制解压资源。不默认反序列化不可信 pickle，不执行下载数据中的脚本。

8. 用临时目录与完成标记保证中断后状态明确。失败的解压不能被识别成已部署。

四、RoboMIND 子集部署

1. 从实际文件树查找真实 h5_franka_1rgb 所在版本和路径，不自动切换到 RoboMIND2.0、其他机械臂、RGB-only 转换版或仿真数据。

2. 第一轮目标为至少 2 个任务、合计 10 条完整轨迹，优先覆盖官方 train/val；根据实际下载单元、文件大小和 RGBD 完整性确定选择，记录固定清单。达不到时如实报告数量。

3. 若上游按大压缩包发布，必须按实际打包结构计算最小可下载单元，不能声称只下载了若干 HDF5 就一定只产生相应网络流量。

4. 首先检测这些候选字段，以实物文件为准：

   observations/rgb_images/camera_top
   observations/depth_images/camera_top
   master/joint_position
   puppet/joint_position
   puppet/end_effector

5. 不把 HDF5 的 shape=(T,), dtype=object 误当成缺少图像维度。根据官方示例和实际编码识别压缩字节，逐帧解码，深度必须保留原位深。错误样本隔离并记录。

6. 官方说明 h5_franka_1rgb 涉及 BGR 色序。核验读取库输出与编码约定，统一得到 RGB；必须防止重复交换通道，加入已知色块单元测试。

7. 检查 RGB/深度是否非空、可解码、帧数和对应关系是否成立；空 depth group、损坏数据、全零深度不能进入有效 RGBD 集。

8. 深度单位转换依据锁定版本的说明、文件属性和校准信息。原始深度保留；统一深度以米表示，并记录比例来源。数值范围只做异常提示，不能仅凭 max>100 自动猜单位并宣称几何正确。

9. 区分 master 控制侧信息与 puppet 实际状态，核实关节顺序、夹爪含义、单位及末端姿态约定。不得把八个元素全部当作旋转关节，也不得无依据把某组状态称为真实 action label。

10. 核验时间戳、采样率、RGB/深度同步与相机标定。缺内参、外参或同步证据时保留可读数据并标记能力受限，不虚构焦距、手眼标定或固定帧率。

11. 不将成功轨迹自动当作失败识别训练集，不凭文件名或模型猜测制造任务进度、失败原因或最佳重规划时刻标签。

五、GraspClutter6D 部署

1. 先下载并读取官方 split_info、README 和文件元数据，按官方划分选择首轮场景。

2. 当前官方发布包含 scenes.7z.001～005。部署时重新核验最新清单与锁定版本；这些是一个场景压缩包的分卷，不是五个独立数据子集。

3. 优先寻找作者当前是否提供可验证的独立场景下载；没有则下载解压所必需的完整分卷。禁止只下载 .001 就当成可用场景数据，禁止无证据声称用普通 HTTP Range 即可随机提取任意压缩场景。

4. 完整分卷齐备后进行 archive test/listing；先选择约 10 个场景做 smoke 解压及验收。网络仍可能需要完整分卷，报告必须将下载量与保留场景量分开。

5. 根据目标场景及任务下载必要的 split、物体模型、抓取和碰撞标签。默认不下载同一模型所有重复格式；官方抓取评测依赖不完整时标记评测不可用，不能以读到 RGBD 代替抓取评测通过。

6. 按实际格式读取 rgb、depth、scene_camera.json、scene_gt.json、scene_gt_info.json、mask、visible_mask、label 等；完整性按实际启用的任务配置检查。

7. 深度保留 16 位原始值，按官方/BOP 的 depth_scale 语义统一为米；不要固定除以 1000 后又乘除一遍比例。相机内参必须对应相应相机、图像和分辨率。

8. 解析官方相机编号、标定与帧编号关系；不得把不同视角的编号序列当作机械臂执行时间序列。

9. 明确物体位姿、相机位姿、抓取位姿的坐标系和变换方向。验证矩阵、长度单位；区分毫米版和米版模型，避免 1000 倍尺度错误。

10. 区分物体 ID、实例 ID、完整掩码、可见掩码；保留同一图像中的重复实例。没有 action/robot_state 就保持为空，不能为了统一接口伪造机械臂状态。

11. 可复用官方 graspclutter6dAPI，但先检查依赖兼容性。若旧依赖与项目冲突，隔离官方评测环境；基础 RGBD 读取不能被非必需的官方评测依赖阻塞。

六、统一数据契约与质量门禁

在现有项目命名空间内增加最小必要接口；没有同类模块时才创建 rgbd_data 包。

每个样本至少提供：

- dataset_id、source_revision、task/episode/scene/frame/camera 标识。
- sample_kind：trajectory_observation 或 static_multiview_scene。
- source_file、原始相对路径、文件摘要、原始划分。
- rgb：RGB uint8。
- depth_raw。
- 可确认单位时的 depth_m float32。
- depth_valid_mask。
- 原始尺寸、单位、比例依据、深度有效率与异常统计。
- 原始时间戳/时间基准；没有时间戳时保存 frame_index 并标记未知。
- K_rgb、K_depth、畸变参数、RGB-Depth 对齐状态及依据，可为空。
- 明确命名与方向的坐标变换，可为空。
- robot_state、action 与各自语义/单位，可为空且必须分别记录。
- annotations：分割、位姿、抓取等单独保存，不混入普通模型输入。

不存在的机器人基座外参不得补单位阵。

能力门禁分开记录：

RGBD 可解码；
深度量纲确认；
RGB-Depth 对齐确认；
相机三维几何可用；
机器人基座坐标可用；
时序对齐确认；
动作标签可用；
任务标注可用。

几何处理要求：

- 深度单位或对应内参未知，不生成宣称具有真实尺度的点云。
- 只有对应深度相机的有效 K 和深度语义明确时，才能反投影。
- 缺 RGB-Depth 标定/对齐证据，可以保留深度点云，但不能直接按同像素索引贴彩色。
- 缺相机到机器人基座变换，不能输出基座坐标目标或驱动工作空间安全判断。
- 零值、无穷、NaN 等根据上游规则掩码，不将无效深度补成“无遮挡”或安全空间。

七、索引、划分与训练读取

1. 采用现有索引方案；不存在时以 JSONL 或 SQLite 为主，避免新增数据库服务。图像通过路径/帧索引访问，不把全数据转成 Base64。

2. 保留官方 train/val/test 与协议。RoboMIND 没有官方 test 时不能将 val 改名为官方 test；GraspClutter6D 不混用 cross-object 和 intra-object 协议。

3. 需要验证集时仅从官方训练部分按完整 episode/scene 分组产生，保存 seed 和成员清单；不得拆帧导致同轨迹、同场景多相机跨集合泄漏。

4. 增加跨集合重复 ID、内容重复与相邻序列泄漏检查；官方既有划分出现问题时报告，不静默改写原始划分。

5. 提供两类 loader：
   - RoboMIND 的时间窗口读取。
   - GraspClutter6D 的单场景/多视角读取。
   用共同观察接口，不强行合并成同一种动作学习数据。

6. 采用惰性读取，HDF5 按 worker 独立打开；限制缓存和预取，支持 num_workers=0。不同图像尺寸和缺失字段的 batch 处理明确且有测试。

7. 输出至少一个真实 batch 的形状、dtype、深度有效率、标定可用性、读取耗时与峰值内存。无需下载大模型或启动完整训练。

8. smoke 子集仅用于部署验收，不称为具有统计代表性的训练集或正式基准结果。

八、接入 BIG-small 与本地预览

1. 提供 DatasetObservationProvider 或与现有接口等价的适配器；数据来源显式标为 dataset_replay，只允许测试/仿真或独立离线模式使用。

2. RoboMIND 支持逐帧、暂停、跳转和按明确规则回放；GraspClutter6D 提供场景与相机切换，不能假扮带动作响应的动态仿真环境。

3. 保留原始采集时间与回放时钟映射。不得用当前时间覆盖采集时间，冒充真实实时传感器的新鲜观测。

4. 原始观察与 ground truth 分通道。使用真实标注构造场景摘要时显式标为 oracle/evaluation；不能把标签直送感知模块后报告模型识别准确率。

5. 输出至少各 5 组真实 RGB、带米制色条的深度和有效性掩码预览；有可靠标定才输出点云，有标注才叠加掩码/位姿/抓取。

6. 优先复用现有 dashboard/可视化；不要为部署数据集另建完整 Web 产品。没有合适界面则生成静态 HTML/图片及 CLI 预览，不以 GUI 显示成功作为服务器验收前提。

7. 不将第三方示教动作直接发送给真实硬件，不绕过任务契约、技能执行器、安全盾。离线接入不能更改生产配置默认值。

九、命令入口与文档

沿用现有 CLI；没有则实现 scripts/rgbd_data.py，至少提供：

- doctor：环境、权限、空间、来源检查。
- plan：固定版本的清单、预算与依赖计划，不下载大文件。
- download：按数据集/profile 下载、续传与校验。
- extract：安全解压、分卷检查与中断恢复。
- validate：RGBD、标定、时序、标注、划分检查。
- index：索引与固定划分清单。
- preview：真实样本的本地可视化。
- smoke：真实 loader 与离线观察接口验收。
- status：按数据集显示已完成范围、阻塞原因与恢复命令。
- deploy：按上述顺序运行的幂等总入口。

增加 configs/rgbd_datasets.yaml 和 .env.example 中必要变量，支持 smoke/pilot/full；这里 full 仅指显式选定的数据范围，不默认等于整个 RoboMIND。

提供 README 快速入口和 docs/rgbd_datasets_deployment.md，写清：
本地目录、授权步骤、预算、执行命令、数据规模、校准缺口、恢复方式、许可证与引用。

所有展示命令必须与实际实现一致，不能文档写一种参数、程序实现另一种。

十、测试与验收

先为关键数据处理写测试，再实现；至少覆盖：

- BGR/RGB 只转换一次、HDF5 编码帧解码、16 位深度保真。
- 毫米/米及 depth_scale 处理、无效深度、单位证据缺失。
- 相机内参缺失、变换方向错误、RGB-Depth 未对齐时的能力降级。
- 空 depth group、坏帧、长度不一致、时间戳缺失。
- 下载中断/重试/恢复、版本不匹配、摘要失败、磁盘预算。
- 分卷缺失、压缩包路径穿越、半解压目录不被判成成功。
- episode/scene 级划分无泄漏，GT 不混入普通模型输入。
- 数据集缺失时明确报错，不用随机数组替代真实数据。
- loader 多 worker 和 CPU 模式。
- 离线 provider 禁止进入生产硬件链路。

合成夹具只能证明代码单元测试，必须标为 synthetic_fixture；真实下载验收必须使用来源可追溯的实际样本，两者分别统计。

CI 默认只执行小型离线测试，不拉取数百 GB 数据、不要求真实 Token；真实数据集集成测试使用独立标记和显式路径。

运行已有格式、lint、类型检查和相关回归测试；报告哪些实际执行、哪些未执行及原因，不以 SKIP 作为 PASS。

十一、最终交付与状态

生成机器可读 JSON 及中文 Markdown 报告，包含：

1. 分支、HEAD、修改文件与已运行命令。

2. 每套数据的官方源、锁定版本、许可证、访问状态、实际存储路径。

3. 下载字节数、压缩包数、真实任务/轨迹/场景/帧数、失败/隔离样本数。

4. RGBD 解码、量纲、标定、对齐、时序、动作、标注的独立检查结果。

5. 索引、split 清单、真实 batch 摘要、预览文件和数据报告路径。

6. 已通过测试数量、失败与跳过项、既有项目是否出现回归。

7. 未完成项、具体阻塞、恢复所需的最小用户操作与可运行命令。

8. 当前可用于哪些训练/验证任务，哪些仍不具备条件。

分别汇报：

software_ready
download_status
rgbd_status
geometry_status
temporal_status
annotation_status
integration_status
verified_scope

只有对应真实数据完成下载、读取、校验与接口测试，才可标记该范围：

SMOKE_VERIFIED
PILOT_VERIFIED
FULL_VERIFIED

授权不足写 BLOCKED_AUTH；
容量不足写 BLOCKED_STORAGE；
网络受阻写 BLOCKED_NETWORK。

原始 RGBD 可读但缺校准时明确为 RGBD_READABLE_GEOMETRY_UNVERIFIED，而不是伪造标定或把全部部署一概写成失败。

现在开始：

先简要给出仓库审查结论和实际下载计划，然后在预算内连续完成实现与执行。

不要反复确认已明确的技术选择。
不要停在安装 SDK 或生成空目录。
不要通过 Mock 冒充两套真实 RGBD 数据部署完成。

若长下载尚未结束，准确汇报下载中/未完成与续传状态，不能因启动下载进程就宣称成功。