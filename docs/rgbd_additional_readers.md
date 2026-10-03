# 新增真实 RGB-D 数据统一读取

已下载的三套来源使用 `prepared_rgbd` 适配器接入 `DatasetLoader`、`DatasetObservationProvider` 和 `scripts/rgbd_data.py`。原件仍在 `$BIGSMALL_DATA_ROOT/downloads`，默认数据根为 `$HOME/datasets/BIGsmall`。派生 PNG、逐帧元数据和完成标记存放在 `raw/<dataset_id>`；转换不覆盖原件，不重新下载。

| dataset_id | 固定选择 | 划分与能力边界 |
|---|---|---|
| `industryshapes_real` | 镜像实际齐备的 370 对，6 场景、771 实例 | 全部保留官方 classic/test。RGB 相机 K、物体 R+t 和源实例记录可读；深度按源说明由 mm 转 m。未确认深度相机注册关系，`K_depth` 与对齐能力不补造 |
| `microagi01_small` | 完整 `open-source-12.mcap`，108 对 | 官方 split 未知。RGB 1920×1080、深度 1280×800，各自 K 和原始静态变换消息保留，深度单位来自包内消息。按日志时间最近邻、10 ms 上限、一对一配对；日志时间不是已确认的采集同步 |
| `vins_rgbd_small` | 完整 `Handheld/Normal.bag`，973 对；末尾 RGB 源帧号 973 未配对 | 使用 RGB 与 `/camera/aligned_depth_to_color/image_raw` 的 uint16 深度，按 ROS header.stamp 精确配对。包内缺 CameraInfo，深度单位未核准，`depth_m=None`；不使用 rgb8 伪彩深度，不凭话题名称宣称像素对齐 |

全部保留原始 uint16。无效掩码排除 0，并采用项目保守策略排除 65535；该策略不表示上游已定义 65535 为无效哨兵。掩码仅表示通过数值规则，不保证物理测量准确；异常大值保留，不按猜测的距离阈值裁剪。上述数据不提供原生机器人动作标签，也不作为执行成功证据。Industry 原 test 的另外 553 帧缺镜像文件，仍记录在[下载阶段的缺失清单](rgbd_additional_downloads.md)。

## 使用命令

当前 `.venv-data` 已具备依赖；环境重建所需依赖列在 `pyproject.toml` 的 `rgbd-data` extra，其中 MicroAGI 解压使用 `backports.zstd`。新读取器支持所选 MCAP 的 protobuf/none/zstd，以及所选 ROS1 bag 的 none/bz2；不执行包内脚本，不依赖 ROS 或 FiftyOne 服务。

```bash
.venv-data/bin/python scripts/rgbd_data.py deploy \
  --dataset industryshapes_real --profile curated --num-workers 2
.venv-data/bin/python scripts/rgbd_data.py deploy \
  --dataset microagi01_small --profile curated --num-workers 2
.venv-data/bin/python scripts/rgbd_data.py deploy \
  --dataset vins_rgbd_small --profile curated --num-workers 2
```

`deploy` 顺序执行本地文件/空间门禁、SHA256 核验、原子转换、全帧质量检查与索引、预览、worker 2/0 smoke。再次运行核验并复用已完成转换。三套新增源的 `download` 子命令也仅核验已有文件，网络流量为 0；文件缺失或摘要不符会报错，重新获取来源文件仍使用[下载阶段入口](rgbd_additional_downloads.md#下载复现)及原物理直连规则。`plan` 不会触发下载；首次转换空间峰值按原文件总量的 8 倍保守估算，并保持 50 GiB 余量，每次派生写入继续检查余量。已有完整派生清单通过核验时，本轮无需再次预留转换空间，余量门禁仍有效。

中断转换保留 `.partial`，不能作为已部署数据读取。同一源和选择可重新转换；选择身份变化或已发布文件遭修改时拒绝复用。MicroAGI 的 `master` 是可变分支，本地复现依靠每个原件的上游 SHA256；VINS 只有本地快照 SHA256，不能称官方哈希认证。原生读取器对当前小包设置资源上限，更大容器须另行评估。

## Python 接口

```python
from pathlib import Path
from cloud_edge_robot_arm.datasets.external.index import load_index
from cloud_edge_robot_arm.datasets.external.loaders import DatasetLoader, read_sample
from cloud_edge_robot_arm.datasets.external.provider import DatasetObservationProvider

root = Path.home() / "datasets/BIGsmall"
rows = load_index(root / "manifests/industryshapes_real-index.jsonl")
batch = next(iter(DatasetLoader(rows, batch_size=2, num_workers=0)))
sample = read_sample(rows[0])  # 包含原始深度、单位依据、能力和独立 annotations

replay = DatasetObservationProvider(rows)
observation = replay.next_observation()  # 普通观察不含 GT 或 action
replay.pause()
replay.seek(0)
replay.resume()
oracle = replay.oracle_annotations()  # 显式、独立的离线评测通道
```

使用多进程 worker 时，从脚本的 `if __name__ == "__main__":` 入口创建 loader。不同原生尺寸不隐式缩放。序列保留源 RGB 帧号、RGB/深度独立时间、未配对清单；`raw/<dataset_id>/conversion.json` 给出配对统计。静态数据没有伪造时间戳。只有一条序列时选取 5 个分散帧预览，报告仍计为 1 个组。

## 本地结果

- 索引：`manifests/<dataset_id>-index.jsonl`
- 配对/转换记录：`raw/<dataset_id>/conversion.json`
- 质量与 worker 报告：`reports/<dataset_id>/quality.json`、`smoke-workers-{0,2}.json`
- 预览：`previews/<dataset_id>/index.html`
- 状态：`reports/<dataset_id>/deployment.json`，选定范围通过时为 `SELECTED_RGBD_VERIFIED`

实际计数、测试结果及限制见[本阶段验收](../artifacts/research/process/20261003-additional-rgbd-readers/acceptance.md)。完整 RoboMIND/GraspClutter 原目标、T3/T4 真实模型与物理技能的状态不随这次数据接入升级。
