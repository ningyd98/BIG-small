# GraspClutter6D 中国大陆直连精选实测记录

已实际准备 **10 个真实场景、40 帧四相机 RGBD**，来自魔搭 [Voxel51/graspclutter6d](https://modelscope.cn/datasets/Voxel51/graspclutter6d)，固定提交 `f6d801ce94dbeaf1a40c19006b741cba7675a101`，许可证 CC BY-SA 4.0。43 个完整来源文件共 **790,485,480 bytes（约754 MiB）**，全部与魔搭提供的 SHA256 一致。原始下载位于 `/home/ningyd/datasets/BIGsmall/downloads/graspclutter6d_curated/modelscope/f6d801ce94dbeaf1a40c19006b741cba7675a101`，不进入 Git。

原精选导出实际包含 99 个唯一场景、111 个场景/视角组、555 个记录（444 RGB + 111 三维场景）。本次按编号顺序取前 10 个有完整四相机 viewpoint=0 的组：`000000, 000001, 000017, 000020, 000034, 000041, 000052, 000059, 000074, 000088`。相机为 RealSense D415、D435、Azure Kinect、Zivid。仅下载 40 张 RGB PNG、完整 samples.json、metadata.json 和许可证卡片，不下载无关 PLY/fo3d。完整样本 JSON 为 638,810,491 bytes，RGB 合计151,650,276 bytes。

传输严格绑定物理网卡 `enp7s0`，使用数字 AliDNS，禁止系统代理或 TUN 回退，TLS 证书校验保持开启。魔搭官方 HTTPS 重定向至其中国 LFS 域名 `cdn-lfs-cn-1.modelscope.cn`，固定接受中国联通河北 `119.249.48.19/20`，下载实测 peer 为 `119.249.48.19`；API peer 为 `47.92.141.220`、`39.99.133.195`。所有下载 socket 的物理绑定及实际 peer 已记录。该 dataset 累计 **802,352,512 bytes** 网络量（含 source 探查和部分 Range 读取）已计入原全局预算账本，未覆盖既有历史。

40 帧实际解码通过：RGB 为 uint8 三通道；深度是 FiftyOne Heatmap 中 `base64(zlib(NPY))` 保存的 **float32 数值毫米深度**，四相机均与对应 RGB 同网格，有限且非负；相同尺寸本身不能证明 RGB/depth 对齐，alignment 保持 unknown。它不是彩色预览。精选作者已应用原相机 scale，因此只乘 `0.001` 成米，不能再次套原 BOP depth_scale；不能声称保留原传感器 uint16。

669 个实例 mask 均为 bool 裁剪矩形，与归一化 bbox 对应像素尺寸一致。检测框、实例 mask、2D grasp polylines 应作为独立 oracle/评测标注。该精选缺少 K、完整 6D pose 矩阵、完整三维 grasp/collision tensors、机器人动作和原采集时间，禁用反投影点云与机器人基座坐标。created_at 是导出日期。选中帧 mean_visibility 为0.642–0.863，适合真实 RGBD 读取、预览和原型验证，不代表完整数据训练或正式 benchmark。

精选自身无官方 split。实际协议为 curated_export，所有帧 official_split=None。本机既有、已验证原 repo 的 grasp_cross_object scene 标签仅保留为对照参考，不应用为精选的官方 split：原 train 为000017、000041，原 test 为000034、000059、000074，其余5个原 unassigned。完整来源摘要见 manifest。

已生成仅含40帧的外部派生投影 `/home/ningyd/datasets/BIGsmall/manifests/graspclutter6d_curated/selected-samples.json`，大小 **56,024,794 bytes**，相邻 provenance 保存原完整 SHA、投影 SHA 和准确选择规则，避免每帧重新解析638MB JSON。它是可追溯投影，不伪称上游原件。大探查文件保留于外部数据根的 source-probes。

本报告证明来源、文件摘要、网络路径和真实 schema，项目 reader/provider/batch/preview 集成验收由主任务另行记录。

证据：[冻结 manifest](/home/ningyd/文档/ChatGPT/BIGsmall/configs/rgbd_sources/graspclutter6d_curated.json)、[40帧 schema 验证](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261003-curated-rgbd/grasp-curated-schema-validation.json)、[下载结果](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261003-curated-rgbd/grasp-curated-download.json)、[物理 socket 证据](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261003-curated-rgbd/grasp-curated-tcp.json)。格式依据：[FiftyOne 序列化 API](https://docs.voxel51.com/api/fiftyone.core.utils.html)、[Heatmap 标签定义](https://docs.voxel51.com/api/fiftyone.core.labels.html)。
