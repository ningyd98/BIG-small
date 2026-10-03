# 真实 RGB-D 精选实际验收

2026-10-03。已按用户“精选集先用”和“大陆镜像、不走隧道”要求，部署魔搭 `Voxel51/graspclutter6d` 的独立变体 `graspclutter6d_curated`。状态为 **`CURATED_RGBD_VERIFIED`**，可用于离线数据读取、标注检查和感知原型。机器证据见[acceptance.json](acceptance.json)，操作见[快速说明](../../../../docs/rgbd_curated_quickstart.md)。

## 实际完成

| 项目 | 实测结果 |
| --- | --- |
| 固定源 | ModelScope `Voxel51/graspclutter6d` |
| revision | `f6d801ce94dbeaf1a40c19006b741cba7675a101` |
| 下载 | 43 个来源文件，790,485,480 bytes，约 754 MiB |
| 摘要 | 全部匹配上游 SHA256，原始 source JSON 保留 |
| RGB-D | 10 个场景 × 4 相机，40 帧有效，0 隔离 |
| 深度 | 数值 float32 毫米，原值保留；仅乘一次 0.001 转米 |
| 实例标注 | 669 个可见实例掩码，尺寸和框匹配 |
| 预览 | 5 个独立场景，RGB、米制深度、有效性掩码；实际检查 PNG |
| 离线接入 | CPU worker 0 和 2 的实际 batch 均通过，GT 独立 |
| 恢复 | 第二次完整 deploy 成功复用 raw，未重下载来源 |
| 软件 | 228 passed，2 个原完整目标用例 skipped，0 failed |
| 静态检查 | Ruff、mypy（15 个源文件）通过 |
| 独立复核 | 必要发现均关闭，见[最终复核](final-review.md) |

相机为 Azure Kinect、RealSense D415、RealSense D435、Zivid；scene IDs 为 `000000, 000001, 000017, 000020, 000034, 000041, 000052, 000059, 000074, 000088`，均为静态 viewpoint 0。这是确定性首批选择，没有按遮挡或可见率反复筛选，未声明统计代表性。

源正文含全部精选导出的深度和标注；完整 `samples.json` 占 638,810,491 bytes。项目仅发布所选 40 帧 RGB 与派生逐帧记录、可见掩码，同时保留完整原正文的摘要绑定。精选 `official_split=None`，索引 split 为 `unknown`；原完整协议的 scene 标签只保存为参考，不应用到精选划分。

## 网络与预算

全部本次真实下载使用 `enp7s0` 物理网卡绑定，数字 DNS、域名门禁与 TLS 校验开启，不使用环境代理或 TUN 回退。来源为 `modelscope.cn` 和 `cdn-lfs-cn-1.modelscope.cn`，实际数据 CDN 对端为中国联通河北地址 `119.249.48.19`。证据包含实际 socket 对端、绑定网卡、来源跳转和逐文件摘要，见[来源审计](sources/curated-grasp-source.json)。

精选累计网络体 802,352,512 bytes，包含 26,359,206 bytes 的前期 metadata/Range/RGB 探查；不是仅按最终文件大小计账。全局账本累计 4,223,889,780 bytes，包含历史完整目标断点与 Robo 小 ZIP。RoboMIND 家族实际新增 180,163,745 bytes，仍低于 10 GiB；全局低于 250 GiB，磁盘保留量大于 50 GiB。原完整目标约 3.24 GB 断点保留，未继续海外下载。实际预算快照见 JSON 报告。

## 证据与使用

外部数据根为 `/home/ningyd/datasets/BIGsmall`。原件及派生数据在 `raw/graspclutter6d_curated/`，索引为 `manifests/graspclutter6d_curated-index.jsonl`，预览为 `previews/graspclutter6d_curated/index.html`。仓库仅保存来源清单、schema 摘要、测试日志及报告，RGB、数组、归档和大型探查副本均放仓库外。

- [实际部署快照](actual-deployment.json)、[质量报告](actual-quality.json)、[下载复用报告](actual-download.json)
- [CPU 0 worker](actual-smoke-workers-0.json)、[CPU 2 worker](actual-smoke-workers-2.json)
- [40 帧独立实际审计](actual-curated-audit.json)、[可复现审计脚本](verify_actual_curated.py)
- [实际首次部署](curated-cli-deploy.log)、[恢复复用](curated-cli-reuse.log)、[软件测试](curated-all-tests.log)
- [直接 Python 使用示例复跑](quickstart-verified.log)：隔离环境本地注册 `src`，无新增网络依赖下载

实际审计还确认每场景四种相机齐备、毫米转米无重复缩放、模型输入没有实例 GT、缺失字段保持为空。首次部署进程内存峰值包含解析完整 JSON 的阶段，CPU smoke 时间和 RSS 仅为此次读取记录，不能作为正式性能基准。

## 未完成的能力与原目标

精选没有 K、深度 optical-z 语义证据、RGB-D 对齐证据、采集时间或机器人状态/动作。40 帧均有公制深度，但几何、时序和动作能力均为 0；不生成点云、不输出机器人基座目标。导出日期不是采集日期。二维抓取线不是完整六维姿态或官方三维抓取/碰撞真值。

同次实际下载的 RoboMIND 官方小 ZIP 含两条 600 帧真实轨迹，但只有 RGB，无深度，标为 `REJECTED_RGB_ONLY`，未发布为 RGB-D；见[实测报告](../20261003-external-rgbd/sources/robomind-curated/real-source-assessment.md)。原完整 RoboMIND 保持 `BLOCKED_BUDGET`，原完整 GraspClutter6D 保持 `BLOCKED_NETWORK`，均为 `NOT_VERIFIED`。精选使用不升级完整数据目标。

软件测试的两项 skip 属于原完整数据集的显式真实数据用例；本次精选真实 CLI 与独立审计实际执行通过，未用 skip 代替验收。此前相关旧路径回归的 122 pass / 1 既有中文注释审计失败保留在[基线证据](../20261003-external-rgbd/existing-audit-failure.json)，未宣称全仓库测试通过。

本次没有模型训练、官方基准分数、抓取闭环、机器人执行或 Sim2Real 结果。数据许可为 CC BY-SA 4.0，原来源及引用保留；未公开上传数据，未提交或推送 Git。
