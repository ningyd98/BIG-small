# 更多国内 RGB-D 来源核查

后续进展：本研究快照之后，三个优先来源的选定完整文件已下载并完成独立离线检查；最新状态见[完整文件验收](../20261003-full-rgbd-download/acceptance.md)。下面的前缀验证与未部署表述保留研究阶段原口径，不代表最新下载状态。

核查日期：2026-10-03。本报告是本轮结论；同目录三个分工报告保留检索过程，其中尚未完成的探测和旧排序以本报告的实测结果为准。

优先补充 **IndustryShapes 的真实部分**，适合物体分割、6D 位姿和带相机内参的几何验证；小体积操作序列可选 **MicroAGI01**；相机同步、反投影与室内序列可选 **VINS-RGBD**。这三个来源已取得真实文件响应，但验证深度不同。本轮没有将新来源接入项目 reader，也没有下载全库。

## 候选与下载粒度

| 顺序 | 来源 | 真实 RGB-D 与标注 | 国内下载粒度 | 本轮验证 |
|---|---|---|---|---|
| 1 | 魔搭 [Voxel51/IndustryShapes](https://modelscope.cn/datasets/Voxel51/IndustryShapes) | 数值深度 PNG、相机内参 K、物体 R+t、mask；classic test 为真实工业采集，classic train 混有合成 | 可按 RGB/depth 单帧选择；samples.json 索引 137,313,312 字节，约 131 MiB；已验一对媒体合计 595,464 字节 | 第 102 帧 RGB 与 uint16 深度完整下载、上游 SHA256 一致；640×480；记录含 K、depth_scale、物体位姿 |
| 2 | 魔搭 [MicroAGI-Labs/MicroAGI01](https://modelscope.cn/datasets/MicroAGI-Labs/MicroAGI01) | 人类第一视角操作；RGB、数值深度、K、外参、手部与相机位姿 | 当前 410 个 uncut MCAP 中最小是 open-source-12.mcap，69,082,845 字节，约 65.9 MiB | 131,072 字节前缀直连成功、MCAP 魔数正确；有界解压确认 color/depth/info/depth-unit/tf_static 主题；未验全文件和完整数值帧 |
| 3 | [上海科技大学 VINS-RGBD](https://robotics.shanghaitech.edu.cn/datasets/VINS-RGBD) | 实拍 D435i RGB、对齐深度、IMU；官方代码有 K 与毫米深度解码 | Handheld/Normal.bag，505,031,296 字节，约 481.6 MiB | 原文件端点直连 206，ROSBAG V2.0 魔数正确；只读 4 KiB 前缀，未验整包 |
| 条件候选 | [GraspNet-1Billion](https://graspnet.net/datasets.html) | 桌面杂乱场景、数值深度、K、物体位姿、6D 抓取与碰撞标注 | 官方最小图像包 train_4.zip 标称 6.3 GB；抓取和碰撞标注另包 | 找到 SJTU JBOX 与百度官方入口；本机物理直连 JBOX 在 HTTP 响应前断开，未证明裸文件可下载 |
| 条件候选 | [TransCG](https://graspnet.net/transcg) | 真实透明物体；RGB、原始与修补深度、K、mask/pose | 官方百度 scenes 11–20 包标称 13.0 GB；另需 149.3 MB info 包 | 国内分享入口存在；未取得匿名文件直链或实测下载 |
| 条件候选 | [Omni6D-Real](https://github.com/3DTopia/Omni6D) | 真实 Azure Kinect 家庭物体 RGB/depth/mask、位姿；作者论文给出真实 K | 官方 OpenXLab 支持按 source-path 选择；Real 包具体路径/体积未核实 | 需 OpenXLab 登录；未实测文件。必须选 Real，不能把合成 Omni6D/CAMERA 算作实拍 |

“国内入口”不等于“文件直连已验”。前三项的文件探测均绑定物理网卡 **enp7s0**，禁用环境代理，保持 TLS 验证，执行域名门禁及逐跳重定向检查。魔搭媒体只跳转到 cdn-lfs-cn-1.modelscope.cn，实际连接 119.249.48.19；VINS 下载只在 robotics.shanghaitech.edu.cn 内跳转，实际连接 59.78.171.28。未使用隧道，也没有改动全局网络配置。

## 适配与质量限制

- **IndustryShapes**：索引中引用的部分深度文件在当前魔搭镜像缺失，例如第 100 帧深度返回 404。需按实际存在的 RGB/depth 成对筛选，不能承诺整个镜像完整。第 102 帧实测成功，immutable revision 为 `560b0dd042bc34945de6798d67d3cb2da7e9de28`。classic test 的真实来源由[作者论文](https://arxiv.org/html/2602.05555v1)证明；必须保留官方 split，不把 test 并入训练。深度存在 0 与 65535：本轮仅记录像素分布，尚未建立该导出版本的无效值和 extended 缩放政策。它没有原生机器人命令或正式抓取候选张量。现有 GraspClutter reader 不支持它的 path-backed depth、K、ground_truth；需要单独适配。
- **MicroAGI01**：当前魔搭没有旧 README 提到的 cut_mcaps，最小文件由本轮全目录排序确定。单文件可做小规模验证，但人类手部姿态不能当机器人关节控制。相机位姿必须检查对应 health/valid 标记，仅在有效块内使用。需要 MCAP topic 解码适配，前缀解压不代表完整 chunk 校验通过。许可为自定义 maginoresell，不能写成 MIT/Apache。
- **VINS-RGBD**：适合 RGB-D 时序与几何验证，不提供桌面抓取真值或操作命令。它是 ROS1 bag，项目 ROS2 环境需要离线读取/导出；用对齐深度对应的相机标定。代码 GPLv3 不等于数据授权，未找到明确独立数据许可。[官方代码](https://github.com/STAR-Center/VINS-RGBD)证明深度 topic、uint16 解码和 /1000 米制转换，整 bag 未下载。
- **GraspNet / TransCG / Omni6D-Real**：官方格式与用途明确，国内平台文件交付仍待核实。GraspNet、TransCG 官方说明限制非商业使用；Omni6D-Real 的数据许可适用范围仍需核对发布包。没有把这些条件来源计为可自动直连部署。

## 可复查下载入口

- Industry 第 102 帧：[RGB 文件](https://modelscope.cn/api/v1/datasets/Voxel51/IndustryShapes/repo?Revision=560b0dd042bc34945de6798d67d3cb2da7e9de28&FilePath=data%2Fdata_0%2F102_rgb.png)、[depth 文件](https://modelscope.cn/api/v1/datasets/Voxel51/IndustryShapes/repo?Revision=560b0dd042bc34945de6798d67d3cb2da7e9de28&FilePath=fields%2Fdepth%2Fdepth_0%2F102_depth.png)、[samples 索引](https://modelscope.cn/api/v1/datasets/Voxel51/IndustryShapes/repo?Revision=560b0dd042bc34945de6798d67d3cb2da7e9de28&FilePath=samples.json)。只完整验证前两件，索引只读了前缀。
- Micro 最小 MCAP：[open-source-12.mcap](https://modelscope.cn/api/v1/datasets/MicroAGI-Labs/MicroAGI01/repo?Revision=master&FilePath=uncut_mcaps%2Fopen-source-12.mcap)。本轮 master 快照，预期完整 SHA256 为 `e1f0d81d90b5fd8fea7f1b293d51b3e18091618949e195cd141232770c784875`；部署前还应固定 revision，完整下载后核验。
- VINS 最小包：[Handheld/Normal.bag](https://robotics.shanghaitech.edu.cn/seafile/d/0ea45d1878914077ade5/files/?dl=1&p=%2FNormal.bag)。只验证前缀，无上游整包 SHA。
- GraspNet train_4：[官方 JBOX](https://jbox.sjtu.edu.cn/l/SHwJVL)、[官方百度分享](https://pan.baidu.com/s/1A3Tyc7l_u9UwgKqhVJSrNg)。本机 JBOX 探测失败，百度交付未验证。
- TransCG：[13.0 GB 数据包](https://pan.baidu.com/s/14PGEaJCjHJewt_Uy7UiSdQ)，提取码 `umim`；[info 包](https://pan.baidu.com/s/1IddfXYOGOhuqw4CjXS0wfg)，提取码 `ncj0`。info 本身不含场景 RGB/depth。
- Omni6D-Real：[官方 OpenXLab](https://openxlab.org.cn/datasets/kszpxxzmcwww/Omni6D)，按[作者说明](https://github.com/3DTopia/Omni6D)登录并先列文件；不要下载 388.9 GB 的混合全库。

## 排除和暂缓

**Voxel51/lingbot-depth-subset 当前魔搭副本不能当完整 RGB-D 使用**：只有 data/ 等局部内容，缺 fields/、samples.json、metadata.json；后两件原文件端点均实测 404。HF 原版字段不能证明国内镜像含这些文件。

[Robbyant/LingBot-Depth-Dataset](https://modelscope.cn/datasets/Robbyant/LingBot-Depth-Dataset) 官方魔搭版有真实 RobbyReal/RobbyVla 与合成 RobbySim，应按真实部分筛选。但主要以 50 GiB 分卷交付，一个可用批次需合并多卷；小尾卷不是独立精选集，当前不适合先用。许可有上下游标签冲突，保留 CC BY-NC-SA 条款核对。

AgiBot Beta 魔搭当前目录没有作者另一平台所述约 7 GB sample_dataset.tar；已列 observation 包约 25 GB，且还需匹配参数和状态动作，不推荐为小样本。RoboMIND2.0 尚未确认某个具体小包确含数值深度。ClearDepth、TransPhy3D、REGRAD 主体、Jacquard 为合成；DAS depth 为 RGB 估计；HOT3D 不提供所需实测深度栅格，本轮不计入实拍 RGB-D 候选。

## 证据与复现

- [结构化结论](research-summary.json)：候选、大小、证据级别、限制、下载预算快照。
- [Industry 整对检查](industry-pair-validation.json)、[对应 HTTP/SHA 记录](verified-pair-probes-results.json)。
- [Micro 完整目录排序](microagi-file-summary.json)、[前缀主题检查](microagi-prefix-schema.json)、[文件 HTTP 探测](final-probes-results.json)。
- [VINS / JBOX HTTP 探测](initial-probes-results.json)、[缺失文件验证](final-probes-results.json)。
- [物理直连探测脚本](probe_sources.py)：每次最多 8 MiB 请求预算，最多 4 workers，每段实际响应体计入既有全局下载账本。复跑会消耗网络额度，不是离线校验。示例：`.venv-data/bin/python artifacts/research/process/20261003-more-rgbd/probe_sources.py artifacts/research/process/20261003-more-rgbd/verified-pair-probes.json`。

原始响应体保存在仓库外 `/home/ningyd/datasets/BIGsmall/source-probes/more-rgbd-20261003/`。本轮累计网络响应体 **1,763,697 字节**，不是下载总库大小；全球账本累计 4,225,653,477 字节，仍受既有 250 GiB 上限约束。本轮只新增研究记录，不增加项目已部署数据集数量。
