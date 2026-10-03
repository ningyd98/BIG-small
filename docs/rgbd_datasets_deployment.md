# 第三方真实 RGB-D 数据部署

本入口部署 RoboMIND 的真实单臂 `h5_franka_1rgb` 与 GraspClutter6D 的固定场景范围，复用项目 `datasets.external` 命名空间。数据读取、索引、预览和 `dataset_replay` 接入均属于离线工作；不启动模型训练、不连接真实机械臂，也不修改 PCSC、ETEAC、AUTO 或生产配置。

用户随后授权“精选集先用”。独立变体 `graspclutter6d_curated` 已实际部署魔搭 `Voxel51/graspclutter6d` 的 10 个场景、40 帧 RGB-D，状态为 `CURATED_RGBD_VERIFIED`；43 个来源文件共 790,485,480 bytes，全部上游 SHA256 校验通过。使用入口见[精选快速说明](rgbd_curated_quickstart.md)，实际证据见[精选验收](../artifacts/research/process/20261003-curated-rgbd/acceptance.md)。以下完整数据目标状态单独保留，精选验收不替代完整目标。

## 当前实际状态（2026-10-03）

软件层离线测试已通过，最新数量与执行范围见验收报告；夹具标记为 `synthetic_fixture`，只能证明代码行为。真实部署状态如下；下载字节数会变化，以最新 [JSON 报告](../artifacts/research/process/20261003-external-rgbd/deployment-report.json)、[中文验收报告](../artifacts/research/process/20261003-external-rgbd/deployment-report.md) 和 `status` 输出为准。

| 项目 | RoboMIND | GraspClutter6D |
| --- | --- | --- |
| 官方源 | ModelScope `X-Humanoid/RoboMIND` | Hugging Face `GraspClutter6D/GraspClutter6D` |
| 固定 revision | `be28d59219430dc8796f221f7fc4c23e113d6a4e` | `973a567efa2f8047e5a40c9113a672e8215bcc1b` |
| 下载状态 | `BLOCKED_BUDGET` | `BLOCKED_NETWORK`，暂无已核准大陆完整镜像 |
| 固定下载单元 | 两任务、68 个分卷，720,810,482,287 bytes（671.31 GiB） | 9 个文件，209,947,108,139 bytes（195.528 GiB） |
| 真实可读取数量 | 目标轨迹 0 条 | 场景 raw 数据尚未解压；可验证场景/帧为 0 |
| RGB-D / 几何 / 时序 / 标注 / 接口 | 均 `NOT_CHECKED` | 均 `NOT_CHECKED` |
| 已验证范围 | `NOT_VERIFIED` | `NOT_VERIFIED` |

RoboMIND 的首轮目标是至少 2 个任务、10 条完整轨迹，但该 revision 的 `benchmark1_0_compressed/h5_franka_1rgb` 只列出 `bread_in_basket`（37 卷）和 `bread_on_table`（31 卷）两个完整压缩包。首卷各为 10 GiB，其余分卷也必须齐备；末卷不是可单独使用的轨迹子集。实际最小来源单元超出已授权的 10 GiB 子集预算，当前保留 `BLOCKED_BUDGET`，没有开始目标轨迹下载。该状态是预算门禁；磁盘实际不足另记 `BLOCKED_STORAGE`。没有改用 RoboMIND2.0、其他机械臂、仿真数据或 RGB-only 示例替代验收。见[来源审计](../artifacts/research/process/20261003-external-rgbd/sources/robomind/source-summary.md)。

GraspClutter6D 已保存约 3.24 GB 的场景首卷、模型、抓取标签和碰撞标签断点，原下载进程目前已停止。原系统策略的小请求曾确认经 Meta TUN 和日本代理出口；用户随后明确要求中国大陆镜像且禁止隧道。下载入口现已强制物理网卡直连，但尚无合格大陆完整文件源，因此保持 `BLOCKED_NETWORK`。当前没有真实 batch、真实样本预览或 `SMOKE_VERIFIED` 证据。两套数据分别记录 `software_ready`、`download_status`、`rgbd_status`、`geometry_status`、`temporal_status`、`annotation_status`、`integration_status`、`verified_scope`；软件测试通过不会自动升级真实数据验收状态。

镜像核查：`hf-mirror.com` 的 9 个固定文件均转到海外 HF Xet；`hf-mirror.net` 可由物理网卡直连，但其官网声明全球 Cloudflare 节点，不能证明大陆文件托管。魔搭 Voxel51 的精选发布与完整归档版本、格式不同，不能混卷；它已按用户后续授权作为独立精选变体部署。完整镜像限制见[镜像证据](../artifacts/research/process/20261003-external-rgbd/sources/mainland-mirror-candidates.json)。

## 目录与隔离环境

数据根目录优先级为 `--data-root` → 已导出的 `BIGSMALL_DATA_ROOT` → `$HOME/datasets/BIGsmall`，最终记录解析后的绝对路径。本机采用 `$HOME/datasets/BIGsmall`，位于 Git 仓库外；绝对路径见本地 JSON 报告：

```text
$BIGSMALL_DATA_ROOT/
  downloads/<dataset>/<source>/<revision>/  原始文件与 .part 续传文件
  raw/robomind/                            保留上游结构
  raw/graspclutter6d/                      固定场景与必要标注
  raw/graspclutter6d_curated/              精选导出来源与逐帧派生记录
  manifests/                              固定计划、下载账本、索引和 split
  processed/                              必要派生数据
  previews/                               本地 PNG / HTML
  reports/                                环境、质量、部署和 batch 报告
  cache/                                  必要缓存
```

从项目根目录创建独立的数据工具环境，使用 Python 3.12 或更高版本。本机已有 `.venv-data`；原项目 `.venv` 与 ROS 2、MoveIt、MuJoCo、Isaac、PyTorch/CUDA 环境保持各自依赖管理。

```bash
python3.12 -m venv .venv-data
.venv-data/bin/python -m pip install -e ".[rgbd-data]"
export BIGSMALL_DATA_ROOT="$HOME/datasets/BIGsmall"
.venv-data/bin/python scripts/rgbd_data.py doctor
```

基础读取与验收可在 CPU 上运行，不要求安装 Torch 或下载大模型。官方 `graspclutter6dAPI` 的旧依赖约束与现有环境不兼容，不安装进项目 `.venv`；本轮使用轻量读取器。官方抓取评测环境及 `dex_models` 未部署，读到抓取标注不能代替官方基准评测通过。

`.env.example` 只提供配置示例。此 CLI 直接读取已导出的环境变量，不自动载入 `.env`；可用 `--data-root /absolute/path` 显式覆盖。Token 由 SDK 的已有安全凭证或环境变量读取，不写入配置、源码、报告或命令参数。

## 预算与固定选择

预算集中在 [configs/rgbd_datasets.yaml](../configs/rgbd_datasets.yaml)，没有另设预算环境变量：

| 配置项 | 默认值 |
| --- | --- |
| `budget.total_download_gib` | 全局新增下载 250 GiB |
| `budget.robomind_download_gib` | RoboMIND 新增下载 10 GiB |
| `budget.minimum_free_gib` | 保留目标文件系统 50 GiB 空闲 |
| `budget.download_workers` | 4 |
| `budget.decode_workers` | 2；CLI 默认采用该值 |
| `budget.retries` | 3 次有限重试 |

`smoke` 和 `deploy` 可用 `--num-workers 0` 或 `--num-workers 2` 显式覆盖 YAML 默认解码 worker 数；总入口会验证 CPU 单进程及配置的多 worker 读取。修改预算时可复制 YAML，再通过 `--config` 指向副本；扩大已授权范围需要先取得相应授权。`smoke`、`pilot`、`full` 均消费固定 source manifest 的显式成员，当前不会自动扩大选择；`full` 不表示整个 RoboMIND。

`plan` 不下载大文件，输出固定文件清单、可复用文件、剩余网络字节、分卷依赖、展开量、空闲空间及预算门禁。展开量未知时，计划按压缩量 3 倍估算并标记 `ESTIMATED`，启动门禁同时计入待下载量和 50 GiB 保留空间；这不保证实际展开容量。完整归档到齐后进行 test/listing，按实际选定成员重算展开量，并在下载与解压时持续检查空间。预算按下载账本统计实际新增网络字节，失败重传也计入。

GraspClutter6D 固定下载 5 个 `scenes.7z.001`～`.005`、`split_info.7z`、`models_m.7z`、`grasp_label.7z`、`collision_label.7z`。五个 scene 分卷组成一个归档，不能把 `.001` 当作已部署场景。尚未核验到官方独立场景下载；即使只保留 10 个 smoke 场景，网络仍需完整必要分卷。

当前锁定 `grasp_cross_object` 协议，保留官方训练场景 `000005`、`000009`、`000013`、`000017`、`000021`、`000025`、`000029`、`000033` 和官方测试场景 `000002`、`000003`。必要物体模型与抓取标注根据这些场景的固定 object ID 清单选择；不下载同一模型的所有重复格式。精确文件、SHA256、场景和 object ID 见 [GraspClutter6D manifest](../configs/rgbd_sources/graspclutter6d.json)；RoboMIND 的固定分卷与阻塞依据见 [RoboMIND manifest](../configs/rgbd_sources/robomind.json)。

## 执行与恢复命令

以下命令均从项目根目录运行。当前 RoboMIND 的 `deploy` 会返回预算阻塞；GraspClutter6D 的 `deploy` 会返回网络源阻塞。仅在核准大陆文件源后才能恢复下载。

```bash
# 检查环境、权限、磁盘和官方源；--offline 只让 doctor 不联网
.venv-data/bin/python scripts/rgbd_data.py doctor --offline
.venv-data/bin/python scripts/rgbd_data.py plan --dataset all --profile smoke
.venv-data/bin/python scripts/rgbd_data.py status --dataset all

# 总入口：计划 → 下载 → 解压 → 校验/索引 → 预览 → 离线 batch
.venv-data/bin/python scripts/rgbd_data.py deploy --dataset graspclutter6d --profile smoke --num-workers 0
.venv-data/bin/python scripts/rgbd_data.py deploy --dataset robomind --profile smoke --num-workers 0
```

需要逐步检查或从中断点恢复时：

```bash
.venv-data/bin/python scripts/rgbd_data.py download --dataset graspclutter6d --profile smoke
.venv-data/bin/python scripts/rgbd_data.py extract --dataset graspclutter6d --profile smoke
.venv-data/bin/python scripts/rgbd_data.py validate --dataset graspclutter6d --profile smoke
.venv-data/bin/python scripts/rgbd_data.py index --dataset graspclutter6d --profile smoke
.venv-data/bin/python scripts/rgbd_data.py preview --dataset graspclutter6d --profile smoke
.venv-data/bin/python scripts/rgbd_data.py smoke --dataset graspclutter6d --profile smoke --num-workers 0
.venv-data/bin/python scripts/rgbd_data.py smoke --dataset graspclutter6d --profile smoke --num-workers 2
.venv-data/bin/python scripts/rgbd_data.py status --dataset graspclutter6d
```

`validate` 同时生成索引；`index` 重新执行真实样本校验和索引，不跳过质量门禁。缺真实数据时会明确报错，不生成随机替代样本。`deploy` 会复用来源、revision、尺寸与摘要均一致的已验证下载；同一数据根目录已有下载进程时，等待该进程完成或终止后再恢复，避免并发修改账本。

下载目录保留版本绑定的 `.part` 与 `.part.json`，全局账本为 `manifests/download-ledger.json`。本机 Hugging Face SDK 1.33.0 在失败路径会删除其内部中间文件，因此大文件使用 SDK 生成固定 revision URL，并由持久 HTTP Range 传输、预算账本和 SHA256 校验管理续传；小文件可使用 SDK 的单文件下载。Range 用于恢复同一完整文件的下载，不能随机提取任意 7z 场景。SDK 仅保留必要元数据，避免再复制一套数百 GiB 缓存。

原始归档下载后逐块计算本地 SHA256；上游有摘要才标记 `UPSTREAM_SHA256_VERIFIED`，仅本地记录摘要时标记 `LOCAL_SHA256_RECORDED`。不同平台或 revision 的同名分卷不混用。TLS 保持校验，重定向到明文传输被拒绝；日志不记录 Token 或认证头。

解压检查所有必需分卷、路径穿越、绝对路径、链接逃逸和展开大小，使用临时目录及完成标记。`raw/<dataset>/COMPLETE.json` 才表示该固定选择完整装配；半解压目录不会通过部署检查。中断后保留原始下载和临时状态，再运行同一 `extract` 或 `deploy`。revision/选择或摘要不匹配时停止并保留现场，不自动删除已有数据。

| 状态 | 恢复所需条件 |
| --- | --- |
| `BLOCKED_AUTH` | 用户在官方页面自行完成访问流程，并配置已授权凭证；代理不代接受条款 |
| `BLOCKED_BUDGET` | 已授权的更大预算与完整存储计划，或作者提供可核验的小下载单元；当前 RoboMIND 保持阻塞 |
| `BLOCKED_STORAGE` | 在已授权目标目录恢复足够空间，或显式选择另一个已有目录；不自动挂载存储 |
| `BLOCKED_NETWORK` / `INTERRUPTED` | 恢复网络后重跑相同命令，保留版本绑定的续传文件 |

RoboMIND 的 HF 镜像为 gated，未认证请求返回 401，联系信息共享条款未接受；该镜像另锁定 `e7ffe31d1fe983a42c3d7b79d192f554fc05b86e`。当前 ModelScope 候选源允许匿名访问，但不据此假定两个平台文件逐字节相同，也不绕过 HF 条款。

## 下载网络约束

配置 `network.mode: direct`、本机物理接口 `network.interface`（此部署为 `enp7s0`）与明确的数字 DNS 地址。DNS UDP 和下载 TCP 都在连接前绑定物理网卡，并读回确认；不调用系统 DNS 或环境代理，绑定失败、假 IP、缺配置、未核准域名或 TLS 失败都会阻断，没有回退到 TUN 的真实下载路径。换机器时需显式填入当地物理接口。当前实现已在 httpx 0.28.1 / httpcore 1.0.9 验证，隔离依赖锁定这两个版本；单设 HTTPTransport.socket_options 不足以保证连接前绑定。

真实 HF 镜像还需逐文件固定上游 SHA256、HTTPS endpoint 和每个重定向域名的来源核验；默认 `hf_endpoint: null` 和空允许列表保持阻塞，不把 HF_ENDPOINT 环境变量当作已批准镜像。HF 凭证不会发送给第三方镜像。端点只是传输地点，原数据来源/revision/SHA 绑定不变，已有断点只有身份一致才可恢复。域名格式或 HEAD 成功不能证明服务器位于大陆，需独立来源证据。

实际小请求确认 ModelScope 走物理网卡且保留 TLS 校验，hf-mirror.com 的海外跳转在连接目标前被阻止；见[直连实测](../artifacts/research/process/20261003-external-rgbd/strict-direct-probe.json)及[独立网络复核](../artifacts/research/process/20261003-external-rgbd/network-policy-review.md)。这些探测未读取归档数据体，不能充当真实数据验收。

## 数据语义与能力边界

共同离线 `DatasetSample` 保留原始来源、revision、相对路径、摘要、官方 split、RGB `uint8`、原始深度、有效性掩码，以及有依据时的米制深度。缺时间戳、相机 K、基座外参、机器人状态或动作时保留 `None`/未知；不能补焦距、固定帧率、当前采集时间、单位基座变换或 action label。该类型不放宽现有实时 `RGBDObservation` 的严格契约。

RoboMIND 读取 `observations/{rgb_images,depth_images}/camera_top`，支持 HDF5 `(T,)` 编码图像帧，深度按原位深解码。官方 OpenCV 示例输出 BGR；项目 Pillow 解码编码图像已得到 RGB，不能再次交换通道，只有明确的原始 BGR 数组转换一次。官方深度声明为毫米，但真实文件 codec、位深、相机对应关系与属性仍待验收。`master` 控制侧、`puppet` 状态与末端 `xyz+rpy` 分开保存；八维关节数据不自动当成八个旋转关节，示教数据不自动当成动作成功或失败识别标签。

GraspClutter6D 使用逐图 `scene_camera.json` 中的 BOP 语义：

```text
depth_m = depth_raw * depth_scale * 0.001
translation_m = BOP_translation_mm * 0.001
```

原始深度保留 16 位。`cam_K` 必须对应实际相机、帧与分辨率；`cam_R_w2c` 为 world→camera，`cam_R_m2c` 为 model→camera，使用的 `models_m` 坐标为米。四类相机为 D415、D435、Azure Kinect、Zivid，每场景 13 个视角；image ID 是视角与相机编号，不是机器人执行时间序列。物体 ID、实例 ID、完整/可见掩码和同图重复实例分开保留。静态多视角数据不提供机器人 state/action，不构造时序控制标签。

质量报告分别统计 RGB-D 可解码、深度量纲、RGB-Depth 对齐、相机三维几何、基座几何、时序对齐、动作与任务标注能力。缺深度量纲或对应 K 不生成真实尺度点云；缺 RGB-Depth 对齐证据不按同像素贴彩色；缺 camera→robot_base 变换不输出基座目标或工作空间安全判断。无效深度不能解释成无遮挡或安全空间。可读但缺几何证据时记录 `RGBD_READABLE_GEOMETRY_UNVERIFIED`。

JSONL 索引为 `manifests/<dataset>-index.jsonl`，同目录 `.splits.json` 保存种子 `20261003`、成员清单和审计。官方 train/val/test 与 cross-object 协议保留；派生验证集仅从官方训练部分按完整 episode/scene 分组产生，命名 `derived_val`。审计检查跨集合组冲突、重复内容和重复 ID；不拆帧或拆相机造成泄漏，也不把 RoboMIND val 改名为官方 test。

`DatasetLoader` 惰性读取、按 worker 独立打开 HDF5；异形图像或可空字段保留列表，不隐式 resize。`RoboMINDWindowLoader` 读取同一 episode/camera/split 的连续帧；`GraspClutterViewLoader` 切换固定场景的多视角。`DatasetObservationProvider` 只接受 `offline` 或 `simulation_test`，支持暂停、跳转和场景/相机选择，保持原始采集时间与单独回放时钟。GT 从 `oracle_annotations()` 的 `oracle_evaluation` 通道访问，不混入普通模型输入，也不据此报告感知模型准确率。

真实验收后，`reports/<dataset>/quality.json` 保存有效/隔离样本及能力计数；`smoke-workers-0.json`、`smoke-workers-2.json` 保存真实 batch shape、dtype、深度有效率、校准能力、读取时间和进程峰值内存。预览为 `previews/<dataset>/index.html` 与各样本 PNG，目标至少 5 个独立组，包含 RGB、带米制色条的深度和有效性掩码。只有已确认几何/标注的样本才生成对应点云或标注叠加。

只有固定真实范围完成下载、校验、划分审计、数量门槛、预览及离线接口验收，才能标为 `SMOKE_VERIFIED`、`PILOT_VERIFIED` 或 `FULL_VERIFIED`。精选变体只标为 `CURATED_RGBD_VERIFIED`，即使用 `--profile full` 也不能升级原目标。精选深度是导出后的 float32 毫米数值，仅乘一次 0.001；不套用原 BOP sensor scale。精选的相机 K、对齐证据、采集时间、机器人动作和官方 split 均缺失，保持未知；标注为实例可见掩码与二维抓取可视化，不是完整六维姿态或官方三维抓取碰撞张量。当前数据子集不具有已证明的统计代表性；本轮不形成模型训练结果、抓取基准成绩、闭环控制或 Sim2Real 结论。

## 官方来源、许可证与引用

来源快照获取于 2026-10-03 UTC，保留在 [sources/robomind](../artifacts/research/process/20261003-external-rgbd/sources/robomind/pinned-source.json) 与 [sources/graspclutter6d](../artifacts/research/process/20261003-external-rgbd/sources/graspclutter6d/pinned-source.json)。以下许可证依据本轮锁定的官方数据卡；数据与派生样本保留在本地，不自动公开发布。

| 数据集 | 官方入口与格式 | 锁定数据卡许可证 | 官方论文引用 |
| --- | --- | --- | --- |
| RoboMIND | [ModelScope](https://www.modelscope.cn/datasets/X-Humanoid/RoboMIND)、[HF 镜像](https://huggingface.co/datasets/x-humanoid-robomind/RoboMIND)、[固定格式说明](https://github.com/x-humanoid-robomind/x-humanoid-robomind.github.io/blob/28ede3eb1bc8a051be76e560a831fe3f0c32319f/static/all_robot_h5_info.md) | Apache-2.0 | Wu 等，*RoboMIND: Benchmark on Multi-Embodiment Intelligence Normative Data for Robot Manipulation*，RSS 2025；[论文](https://arxiv.org/abs/2412.13877)，准确 BibTeX 见[已保存官方 README](../artifacts/research/process/20261003-external-rgbd/sources/robomind/README-modelscope.md) |
| GraspClutter6D | [固定 HF 数据卡](https://huggingface.co/datasets/GraspClutter6D/GraspClutter6D/tree/973a567efa2f8047e5a40c9113a672e8215bcc1b)、[官方格式](https://sites.google.com/view/graspclutter6d/dataset)、[固定 API 源码](https://github.com/SeungBack/graspclutter6dAPI/tree/a7798be8eeee77bf6f328ddeab9f7d6c31e6c977) | CC BY-SA 4.0 | Back 等，*GraspClutter6D: A Large-scale Real-world Dataset for Robust Perception and Grasping in Cluttered Scenes*；[论文](https://arxiv.org/abs/2504.06866)，作者与引用入口见[已保存官方数据卡](../artifacts/research/process/20261003-external-rgbd/sources/graspclutter6d/README.md) |

下载接口依据 [Hugging Face 官方下载文档](https://huggingface.co/docs/huggingface_hub/guides/download) 和本机已安装 SDK 实际行为；深度、相机与位姿语义依据 [BOP 格式](https://github.com/thodan/bop_toolkit/blob/master/docs/bop_datasets_format.md) 及已锁定的上游源码。未知引用或许可证条款不补写。
