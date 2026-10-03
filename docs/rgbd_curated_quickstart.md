# 先用 RGB-D 精选集

本机已部署魔搭 `Voxel51/graspclutter6d` 的 10 个真实场景、40 帧四相机 RGB-D。可用于数据读取、深度预览、实例标注检查和感知原型开发；来源文件约 754 MiB，数据放在仓库外的 `$HOME/datasets/BIGsmall`。实际验收见[报告](../artifacts/research/process/20261003-curated-rgbd/acceptance.md)。

## 直接使用

在项目根目录执行：

```bash
.venv-data/bin/python scripts/rgbd_data.py status --dataset graspclutter6d_curated
.venv-data/bin/python scripts/rgbd_data.py smoke --dataset graspclutter6d_curated --profile curated --num-workers 0
.venv-data/bin/python scripts/rgbd_data.py smoke --dataset graspclutter6d_curated --profile curated --num-workers 2
```

使用浏览器打开 `$HOME/datasets/BIGsmall/previews/graspclutter6d_curated/index.html` 查看 5 个场景的 RGB、米制深度和有效性掩码。GT 叠加另存在各样本目录的 `oracle_overlay.png`，不会写进模型输入。

Python 中可直接读取已完成的索引：

```python
import json
from pathlib import Path
from cloud_edge_robot_arm.datasets.external.loaders import DatasetLoader, read_sample

root = Path.home() / "datasets/BIGsmall"
index = root / "manifests/graspclutter6d_curated-index.jsonl"
rows = [json.loads(line) for line in index.read_text().splitlines() if line]
sample = read_sample(rows[0])
print(sample.rgb.shape, sample.depth_raw.dtype, sample.depth_scale_m)
batch = next(iter(DatasetLoader(rows, batch_size=2, num_workers=0)))
print(batch["rgb"].shape, batch["depth_m"].shape)
annotations = sample.annotations  # 仅供标注检查或 oracle 评估
```

使用 `.venv-data/bin/python` 运行上述脚本。本机隔离环境已用 `bigsmall-source.pth` 注册仓库 `src`，脚本可直接导入；新环境按部署说明安装项目包。读取器不依赖 FiftyOne、MongoDB 或 GPU。不同分辨率的 batch 保留列表，不自动缩放；静态多相机视图不作为连续动作轨迹。

## 固定范围与能力

| 内容 | 实际状态 |
| --- | --- |
| 来源 | ModelScope `Voxel51/graspclutter6d` |
| revision | `f6d801ce94dbeaf1a40c19006b741cba7675a101` |
| 选择 | 数字顺序前 10 个四相机完整场景，viewpoint 0 |
| 相机 | Azure Kinect、RealSense D415、RealSense D435、Zivid |
| 深度 | 源 float32 毫米数值，乘一次 0.001 转米 |
| 标注 | 669 个实例可见掩码、检测框、二维抓取可视化 |
| 标定与时间 | K、RGB-D 对齐证据、采集时间未知 |
| 控制标签 | 无机器人状态和动作标签 |
| 数据划分 | 精选导出未声明官方 split，索引保持 `unknown` |
| 验收范围 | `CURATED_RGBD_VERIFIED`，用于离线原型 |

缺少相机内参及深度几何语义证据，不能据此生成可靠点云或机器人基座目标。二维抓取线不能作为完整三维抓取或碰撞真值。此精选不能替代官方完整训练集或基准评测，也没有统计代表性结论。

同次检查的 RoboMIND 官方小 ZIP 含两条真实轨迹，但只有 RGB，没有深度，已标为 `REJECTED_RGB_ONLY`，未计入 RGB-D。原完整 RoboMIND 与 GraspClutter6D 的阻塞和断点见[部署说明](rgbd_datasets_deployment.md)。

## 复现

```bash
.venv-data/bin/python scripts/rgbd_data.py deploy --dataset graspclutter6d_curated --profile curated --num-workers 2
```

命令复用已通过摘要校验的下载，逐文件固定版本和来源；新机器需按[部署说明](rgbd_datasets_deployment.md)安装隔离环境，并配置当地物理网卡。直连仅允许魔搭及已验证的大陆 CDN，绑定失败即阻断，保留 TLS 校验，无代理或 TUN 回退。默认保留 50 GiB 磁盘空间，不自动扩大到全量数据。数据许可为 CC BY-SA 4.0；来源与引用见[来源报告](../artifacts/research/process/20261003-curated-rgbd/sources/curated-grasp-source.md)。
