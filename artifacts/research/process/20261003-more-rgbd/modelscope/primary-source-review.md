# ModelScope 真实 RGBD 候选核对

> 本报告为分工检索快照，最终实测结果见 [本轮汇总结论](../research-summary.md)。Micro 最小文件现已确认是 open-source-12.mcap（69,082,845 字节）；当前魔搭 LingBot 精选缺深度和索引，不能作为可用 RGB-D 推荐。VINS 体积为 481.6 MiB。

核对日期：2026-10-03。负责范围为 primary-source 文档与本轮 MS API 快照核对；未进行外网 shell 访问、数据下载或代码变更。国内直连、重定向与原件解码以主任务的物理网卡探测记录为准，域名本身不证明下载落地在大陆。

| 顺序 / 状态 | 准确 ModelScope 仓库 | 真实数据、数值深度与 K | 位姿 / 抓取标注 | 许可 | 实际可选粒度 / 阻碍 |
|---|---|---|---|---|---|
| 1，优先 | [Voxel51/IndustryShapes](https://www.modelscope.cn/datasets/Voxel51/IndustryShapes) | real test、extended_onboarding、extended_office；640×480 RGB、path-backed 16-bit depth PNG、camera_intrinsics 3×3、depth_scale。classic train 混有合成 | ground_truth 中 object-to-camera R、translation_mm、obj_id、mask、visibility；未发现正式 grasp 候选张量 | MIT | MS StorageSize 3,436,877,084 B；samples.json 137,313,312 B，metadata.json 17,679 B。读取一次索引后按单张 RGB/depth 取样，无需全库。具体最小媒体大小由所选 record 决定 |
| 2，真实但最小块过大 | [Robbyant/LingBot-Depth-Dataset](https://modelscope.cn/datasets/Robbyant/LingBot-Depth-Dataset) | RobbyReal 与 RobbyVla 为真实；rawdepth 与 gtdepth 是毫米 16-bit PNG，intrinsic.txt；RobbySim / RobbySimVal 为合成 | RobbyVla 来自 Franka / UR7e 操作场景；发布说明未提供物体 6D pose 或正式 grasp 张量 | MS License 字段 CC-BY-NC-SA-4.0；HF 上方 metadata Apache-2.0 与正文 CC BY-NC-SA 4.0 有冲突，MS 字段更明确 | 分卷 tar.zst。RobbyVla batch0001 为 50 GiB + 50 GiB + 8,235,925,564 B；不能把末卷视为独立小样本。当前完整原件校验 intake 不接收只读 archive prefix，因此不建议先下载 |
| 3，真实动作备选 | [MicroAGI-Labs/MicroAGI01](https://www.modelscope.cn/datasets/MicroAGI-Labs/MicroAGI01/) | 真实人类第一视角操作；JPEG RGB、PNG depth；camera color/depth info 含 intrinsics，depth unit topic 指定毫米 | camera 6DoF、手腕与手指 landmarks、任务分段；未发现物体 CAD 6D pose / 机器抓取候选 | maginoresell / Open Use, No-Resale 自定义许可 | MS 总 2,730,932,847,411 B。实际 tree 只有 uncut_mcaps/，没有 README 所称 cut_mcaps/；最小 uncut MCAP 尺寸尚不在本审阅证据中。preview MP4 不含数值深度 |
| 排除当前镜像 | [Voxel51/lingbot-depth-subset](https://www.modelscope.cn/datasets/Voxel51/lingbot-depth-subset) | HF 原版是完整 RGBD/K；当前 MS pinned revision 根目录仅 data/、README、dataset_infos.json、.gitattributes | 原版未提供物体 pose/grasp | 镜像 Apache-2.0 标识，但上游数据许可冲突见上一行 | MS 缺 fields/、samples.json、metadata.json；提交说明为上传中断后部分提交。不能把 HF card 的深度 / K 视为 MS 镜像已有文件 |

## IndustryShapes 实拍筛选证据

[作者论文 §III-B](https://arxiv.org/html/2602.05555v1#S3.SS2) 明确：classic train 包含 D455 实验室实拍 1,217 张、工业实拍 1,122 张和 Object 3 的 OpenGL 合成 1,361 张；classic test 为 923 张真实工业图像、8 个场景。原文短证据："The test set consists of 923 images"。

extended_onboarding 的 10 条序列（每物体 2 条、约 6.3k 帧）与 extended_office 的 3 个办公室 test 场景（超过 2k 图像）均由手持 D405 实拍；作者说明全部数据具有 RGB、depth、6D pose 和 masks，遵循 BOP 格式。[作者项目页](https://pose-lab.github.io/IndustryShapes/) 和 [原始数据卡](https://huggingface.co/datasets/POSE-Lab/IndustryShapes) 可交叉核对。

安全的实拍选择条件是 split=test，或 dataset_subset 属于 extended_onboarding / extended_office。不要只选 classic train 并称全部真实。Objects 1 和 3 为工业工具，2、4、5 为装配零件；作者使用编号，未给可可靠采用的日常物名。

[Voxel51 导出卡](https://huggingface.co/datasets/Voxel51/IndustryShapes) 与本轮 MS ReadmeContent 给出 map_path、camera_intrinsics、depth_scale 与 ground_truth 字段；父任务已解析实际 MS record 看到这些字段。数值单位最终须以所选 PNG 原值与 depth_scale 约定核对，避免把已经换算的毫米图再次乘比例。Heatmap 的可视化 range 不等于原值单位证据。MS tree 的提交记录提到 fields/depth/depth_7/533_depth-7.png 被内容审核回退，应逐个确认所选文件真实存在。

MS pinned revision：560b0dd042bc34945de6798d67d3cb2da7e9de28。证据快照：[industry-info.json](../industry-info.json)、[industry-tree.json](../industry-tree.json)。

## LingBot 与 MicroAGI 的文件证据

LingBot 作者 [GitHub Data Release](https://github.com/robbyant/lingbot-depth#data-release) 直接指向上述准确 MS 官方 ID；[原始数据卡](https://huggingface.co/datasets/robbyant/mdm_depth) 给出真实机器人 / 多传感器目录及内参文件。[MS 官方快照](../lingbot-original-info.json) 的卡中有短证据："Ground truth depth maps (16-bit PNG, unit: mm)"、"Camera intrinsic parameters"。实际 [官方 MS tree](../lingbot-original-tree.json) 显示分卷大小。HF 原库 2.71 TB 是数据卡描述，不能当 MS 当前实际 StorageSize。

Voxel51 子集的深度在 HF fields/、K 在 samples.json；这些文件并未上传至本轮 MS 根目录。MS pinned revision：53ea7960af28b56af8f1aee90095aa4253a01af0。[MS 卡快照](../lingbot-info.json)、[MS tree](../lingbot-tree.json)、[HF 子集卡](https://huggingface.co/datasets/Voxel51/lingbot-depth-subset)。

MicroAGI 的 [MS 原始卡](https://www.modelscope.cn/datasets/MicroAGI-Labs/MicroAGI01/) 列出 /camera/color/info、/camera/depth/info、/camera/depth/unit_of_depth_in_mm 与 /tf_static；单个完整 MCAP 可携带 RGBD、K、外参、任务与人类姿态。卡的 recordings / task types 总数前后不一致，本文不据此下结论。实际目录以 [microagi-tree.json](../microagi-tree.json) 为准。[许可原件](https://huggingface.co/datasets/MicroAGI-Labs/MicroAGI01/blame/main/LICENSE) 标明可合法使用、模型训练与内部商业使用，但数据付费转售受限；仅记录许可特征，不作法律解释。

## 现有轻量 FiftyOne reader 适配判断

[fiftyone_curated.py](../../../../../src/cloud_edge_robot_arm/datasets/external/fiftyone_curated.py) 当前硬编码 graspclutter6d_curated 与 camera/viewpoint 身份，读取 detections 和 BSON 内嵌 depth.map，不读取 IndustryShapes 的 path-backed depth.map_path、ground_truth 或 camera_intrinsics；不能直接切换 dataset_id 后宣称已支持。

后续可新增很小的 IndustryShapes adapter，沿用现有 relative-path 安全校验、revision / SHA256 绑定及 cropped-mask 展开逻辑。必要差异仅为 scene_id/image_id/subset/split 身份、PNG 原深度加载、按实际 depth_scale 得到米、K 与 R+t 的显式映射。保持真实 split、无机器人控制字段和无 grasp 张量的事实。无需安装 MongoDB 或 FiftyOne，本轮未改代码。

## 不应新增为真实 RGBD 推荐

- Voxel51/ClearDepth、Voxel51/TransPhy3D、Voxel51/widedepth：各自原始卡明确包含合成图像 / 渲染流程，未满足此轮实拍要求。
- GenRobot.AI/DAS-Sample-Data：depth 来自 RGB 估计，未证明实测 depth。
- HOT3D：[BOP 官方表](https://bop.felk.cvut.cz/datasets/) 标为 RGB / monochrome hand-object 数据，不提供实测 RGBD；点云不等于传感器 depth raster。
- Voxel51/ycbv 与 Voxel51/tless：父任务直连 API 已确认 404。没有找到可核实的 Voxel51 HOPE / HomebrewedDB 国内完整 RGBD repo，不能把猜测 ID 当已存在 mirror。原始 BOP 格式有 depth/K/pose，也不证明其 ModelScope 导出完整。
- Voxel51/graspclutter6d 已部署，本轮不重复作新增候选。RoboMIND1.0 保留此前 671 GB 阻塞；原始 H5 文档的 depth 字段不等于当前 MS 每份文件已有 depth。
