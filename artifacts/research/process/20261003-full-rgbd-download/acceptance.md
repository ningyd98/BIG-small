# 新增 RGB-D 完整选定文件验收

日期：2026-10-03。状态：`COMPLETE_SELECTED_FILES_RGBD_OFFLINE_VERIFIED`。

承接用户“精选集先用”和“完整下载”，本轮已完整下载三个新增来源的选定文件，而不是各来源全库。总计 **748 个原始文件、972,121,479 字节，约 927.09 MiB**；747 件魔搭文件通过上游 SHA256，VINS 一件通过完整大小、bag 结构/索引和本地 SHA。数据全部位于仓库外 `/home/ningyd/datasets/BIGsmall/`。

| 来源 | 已完整取得的选定范围 | 实际离线校验 | 当前来源/几何边界 |
|---|---|---|---|
| IndustryShapes | 完整 source index/schema/card + 固定镜像全部可用真实 classic/test 配对；370 帧、6 场景、771 实例；740 媒体文件约 248.52 MiB | 每件文件上游 SHA、480×640 RGB uint8、数值深度 uint16、实例 mask 全通过；6 场景预览已查看 | 原始 test 923 帧中553帧缺镜像文件，未宣称原库完整；65535 和像素配准的物理语义仍待确认 |
| MicroAGI01 | 最小完整 uncut MCAP 65.9 MiB，另有 README、LICENSE、任务映射 | 完整结构边界、58 zstd chunk CRC、summary CRC通过；108 RGB＋108深度；实际深度单位1 mm、两套K及静态外参 | RGB/depth 原生分辨率不同，未作像素配准；人类示教不是机器人控制命令 |
| VINS-RGBD | 完整 Handheld/Normal.bag，481.6 MiB | 全部2,924 bz2 chunks、8,238消息索引、26,197消息结构通过；974 RGB、973标准aligned数值深度；首对时间戳一致 | 包内无CameraInfo，需要匹配外部标定；作者未提供上游SHA，记录的只是本地快照摘要 |

Industry revision 固定为 `560b0dd042bc34945de6798d67d3cb2da7e9de28`，官方 test split 保留。当前魔搭镜像缺深度475、缺RGB157，其中79帧两者皆缺；553条缺失记录单独保存在 `/home/ningyd/datasets/BIGsmall/manifests/industryshapes_real/selection/quarantine.json`。未因缺失重新宣称这是完整官方测试集或代表性采样。

## 下载与读取路径

- Industry：[六场景预览](/home/ningyd/datasets/BIGsmall/reports/industryshapes_real/index.html)，原件目录 `/home/ningyd/datasets/BIGsmall/downloads/industryshapes_real/modelscope/560b0dd042bc34945de6798d67d3cb2da7e9de28/`。
- Micro：[RGB/深度预览](/home/ningyd/datasets/BIGsmall/reports/microagi01_small/index.html)，完整文件 `/home/ningyd/datasets/BIGsmall/downloads/microagi01_small/modelscope/master/uncut_mcaps/open-source-12.mcap`。
- VINS：[RGB/深度预览](/home/ningyd/datasets/BIGsmall/reports/vins_rgbd_small/index.html)，完整文件 `/home/ningyd/datasets/BIGsmall/downloads/vins_rgbd_small/public_https/Normal-bag-505031296-20261003/Handheld/Normal.bag`。

离线工具与复现命令见[新增完整文件使用说明](../../../../docs/rgbd_additional_downloads.md)。尚未把这些来源接入应用统一 reader；现有已接入的 GraspClutter 精选40帧仍保持原状态。本轮没有模型训练、点云精度、机器人执行或硬件验收。

## 网络和预算

本机 DNS/TCP 均绑定物理 **enp7s0**，禁用环境代理，保持 TLS 证书验证、精确 HTTPS 域名门禁和重定向校验；未使用隧道或修改全局网络配置。下载统一使用互斥账本锁，最多4workers，离线校验CPU限制0/2。

本轮文件与目录元数据实际读取响应体 **972,537,579 字节**。截至验收，全局累计5,198,191,056字节，低于250GiB上限，磁盘50GiB保留门槛通过。选定748文件均为VERIFIED，无残留partial。旧完整GraspClutter约3.24GB断点保留；原RoboMIND仍BLOCKED_BUDGET、原GraspClutter全归档仍BLOCKED_NETWORK，本轮不升级原库状态。

## 证据

- [结构化验收](acceptance.json)，含文件数、字节、预算、路径、限制和证据摘要。
- [Industry完整索引下载](industry-index-plan-download.json)、[全部配对下载](industry-media-plan-download.json)、[370帧全量检查](industry-validation.json)。
- [Micro完整下载](microagi-plan-download.json)、[MCAP实际校验](microagi-validation.json)。
- [VINS完整下载](vins-download.json)、[bag实际校验](vins-validation.json)。
- [独立工作流复核](workflow-review.md)、[执行记录](progress.md)。

本轮应用源码未修改。所有本轮离线工具Ruff检查、Python语法检查、JSON/证据摘要核对及`git diff --check`通过；数据验收为上述完整文件实际解码检查，不以模拟测试代替真实数据。
