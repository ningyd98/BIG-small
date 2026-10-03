# 新增 RGB-D 完整文件

本轮承接“精选集先用”：完整下载选定的小包及可用真实配对，而不是各来源的 TB 级全库。下载与离线检查记录在 [本轮验收目录](../artifacts/research/process/20261003-full-rgbd-download/)。所有本机下载绑定物理网卡 `enp7s0`，保持 TLS 校验、重定向域名门禁及全局响应体预算；不走代理或隧道。原始文件保存在仓库外 `/home/ningyd/datasets/BIGsmall/downloads/`。

## 下载范围

| 来源 | 选定完整文件 | 原始文件目录 | 校验边界 |
|---|---|---|---|
| 魔搭 IndustryShapes | 完整索引、schema、README，以及当前镜像实际存在的全部 370 对真实 classic/test RGBD（740 媒体文件、260,594,428 字节） | `industryshapes_real/modelscope/560b0dd042bc34945de6798d67d3cb2da7e9de28/` | 文件均绑定上游 SHA256；保留官方 test split；原始真实 test 共 923 帧，当前镜像缺少 553 帧所需文件，不能称原库完整 |
| 魔搭 MicroAGI01 | `uncut_mcaps/open-source-12.mcap`，69,082,845 字节；另有 README、LICENSE、task_mapping.csv | `microagi01_small/modelscope/master/` | 分支可变，但每件文件固定上游 SHA256；完整 MCAP 结构、压缩块与摘要 CRC；108 RGB、108 数值深度；约 3.80 秒 |
| 上海科技大学 VINS-RGBD | `Handheld/Normal.bag`，505,031,296 字节 | `vins_rgbd_small/public_https/Normal-bag-505031296-20261003/` | 完整文件大小与 bag 结构/索引；仅记录本地 SHA256，作者没有发布可用的上游 SHA |

Industry 的完整 `samples.json` 为 137,313,312 字节。筛选目录位于 `/home/ningyd/datasets/BIGsmall/manifests/industryshapes_real/selection/`，包含选中标注、明确文件清单及 `quarantine.json`。370 对覆盖 6 个场景和 771 个物体实例；缺失计数为缺深度 475、缺 RGB 157，其中 79 帧两者皆缺。

后续开发已将三套来源接入应用统一 reader、索引、CPU 0/2 worker、预览和离线回放，共 1,451 对 RGBD。统一入口见[新增读取器说明](rgbd_additional_readers.md)，本页保留原件下载与独立格式校验的复现方法。

## 本地离线读取与检查

MicroAGI 的 RGB 和深度分别为 1920×1080、1280×800；有两套相机内参与静态外参，深度原值单位为 1 mm。保留原生分辨率，不宣称像素已配准。其人体/手部姿态不是机器人执行命令，使用相机或手部位姿前需检查 health/valid 消息。数据许可为作者自定义 maginoresell，完整许可原件随包保存。

VINS 是 ROS1 bag。实际包含 RGB 和 `16UC1` 对齐深度，以及 IMU/外部位姿。`depth/image_rect_raw` 在这个包里是 `rgb8` 可视化，不是数值深度；应使用 `/camera/aligned_depth_to_color/image_raw`。包内没有 CameraInfo，几何计算还需核对作者代码中的标定是否匹配此序列，不能把外部参考内参冒充实际包内标定。代码的 GPLv3 不等于独立数据授权。

Industry 使用 PNG 数值深度和独立的 K、物体 R+t、cropped mask 标注。本轮只选 `dataset_subset=classic` 且 `split=test`，`depth_scale=1.0`。记录深度 0 与 65535 的出现情况；65535 的物理有效性与 RGB/depth 像素对齐仍待来源确认，不直接生成或宣称验证点云。

离线工具无需安装 FiftyOne/MongoDB、MCAP 或 ROS Python 包；使用当前 `.venv-data` 的 NumPy/Pillow/已有 zstd，以及系统 liblz4。示例：

```bash
taskset -c 0,2 .venv-data/bin/python \
  artifacts/research/process/20261003-full-rgbd-download/verify_microagi.py \
  /home/ningyd/datasets/BIGsmall/downloads/microagi01_small/modelscope/master/uncut_mcaps/open-source-12.mcap \
  --output /home/ningyd/datasets/BIGsmall/reports/microagi01_small

taskset -c 0,2 .venv-data/bin/python \
  artifacts/research/process/20261003-full-rgbd-download/verify_vins.py \
  /home/ningyd/datasets/BIGsmall/downloads/vins_rgbd_small/public_https/Normal-bag-505031296-20261003/Handheld/Normal.bag \
  --output /home/ningyd/datasets/BIGsmall/reports/vins_rgbd_small \
  --report artifacts/research/process/20261003-full-rgbd-download/vins-validation.json

taskset -c 0,2 .venv-data/bin/python \
  artifacts/research/process/20261003-full-rgbd-download/select_industry.py validate \
  --selection-dir /home/ningyd/datasets/BIGsmall/manifests/industryshapes_real/selection \
  --raw-root /home/ningyd/datasets/BIGsmall/downloads/industryshapes_real/modelscope/560b0dd042bc34945de6798d67d3cb2da7e9de28 \
  --output-dir /home/ningyd/datasets/BIGsmall/reports/industryshapes_real
```

上述命令读取本地原件并更新校验报告，不联网下载；本轮实际执行的结果见[验收记录](../artifacts/research/process/20261003-full-rgbd-download/acceptance.md)。

## 下载复现

魔搭下载入口封装在 `run_ms_downloads.py`，可传入同目录 `industry-index-plan.json`、`industry-media-plan.json`、`microagi-plan.json`。文件版本、尺寸、上游 SHA 和物理网络规则都在清单里。已有账本中 VERIFIED 文件会核对本地 SHA 后复用，未完成文件保留续传身份；每段重传字节继续计入全局预算。

VINS 下载脚本为 `download_vins.py`，来源真实标记为 `public_https`，不会伪装成魔搭。源没有不可变版本或官方 SHA，因此保留本地摘要与完整结构检查的边界。当前下载使用首次传输；未来恢复未验证的旧 partial 时不能仅凭本地 SHA 假定来源未变化，应重新取得完整文件或绑定响应版本。

此轮不训练模型、不发机器人执行命令，也不变更之前的完整 RoboMIND/GraspClutter 原库阻塞状态。
