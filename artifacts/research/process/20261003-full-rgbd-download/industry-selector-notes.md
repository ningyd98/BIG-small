# IndustryShapes 完整实拍测试范围筛选记录

日期：2026-10-03。此处是离线筛选工具的证据与使用说明；实际传输、流量账本和下载完成状态以主任务的验收记录为准。

固定来源为魔搭 `Voxel51/IndustryShapes`，revision `560b0dd042bc34945de6798d67d3cb2da7e9de28`。完整 `samples.json` 的 137,313,312 字节及 SHA256 已核验，索引包含 13,012 条记录。其中 `dataset_subset=classic` 且 `split=test` 恰好 923 帧、8 个官方场景，全部保留原有 test split。

两个相关父目录 `data/data_0`、`fields/depth/depth_0` 完整分页枚举后有 843 个 RGB 文件、491 个深度文件。与完整索引连接得到 370 对可下载 RGBD、740 个媒体文件，共 260,594,428 字节。其余 553 帧隔离：475 帧缺深度、157 帧缺 RGB，两项计数存在重叠。可用完整配对覆盖 6 个场景，官方 000006 和 000007 场景没有完整可用配对。因此它是当前国内镜像全部可用的真实 classic test 配对，并非原始测试集全量。

记录原件和内嵌 mask 均保存在数据根目录，仓库只保存不含媒体的摘要：

- `/home/ningyd/datasets/BIGsmall/manifests/industryshapes_real/selection/download-manifest.json`：逐文件路径、来源大小、来源 SHA256。
- 同目录 `selected-samples.json`：370 条完整原始标注。
- 同目录 `quarantine.json`：553 条缺失及原因。
- [industry-selection-evidence.json](industry-selection-evidence.json)：场景、物体、缺失统计及清单 SHA256。

工具不联网，不修改全局下载账本。它先核验完整源索引，检查来源 revision、目录枚举完备声明、路径、K、depth_scale、物体到相机 R 和毫米平移，再输出逐文件下载清单。后续 `validate` 独立检查所有成品 SHA256、RGB uint8、深度 uint16、源声明尺寸与实例 mask，并生成每场景 RGB／深度显示／mask 预览。

```bash
.venv-data/bin/python artifacts/research/process/20261003-full-rgbd-download/select_industry.py select \
  --samples /home/ningyd/datasets/BIGsmall/downloads/industryshapes_real/modelscope/560b0dd042bc34945de6798d67d3cb2da7e9de28/samples.json \
  --inventory artifacts/research/process/20261003-full-rgbd-download/industry-classic-test-inventory.json \
  --output-dir /home/ningyd/datasets/BIGsmall/manifests/industryshapes_real/selection

.venv-data/bin/python artifacts/research/process/20261003-full-rgbd-download/select_industry.py validate \
  --selection-dir /home/ningyd/datasets/BIGsmall/manifests/industryshapes_real/selection \
  --raw-root /home/ningyd/datasets/BIGsmall/downloads/industryshapes_real/modelscope/560b0dd042bc34945de6798d67d3cb2da7e9de28 \
  --output-dir /home/ningyd/datasets/BIGsmall/previews/industryshapes_real
```

923 条候选的身份、K、scale 和 R+t 字段检查均通过。下载完成后，工具绑定 CPU 0／2 对 370 帧、740 个媒体文件完整执行读取、大小／SHA、dtype／shape 和 771 个实例 mask 检查，全部通过。6 个场景各生成一张 RGB／深度／mask 预览，查看总览后视觉 QA 通过。最终报告见 [industry-validation.json](industry-validation.json)，外部预览入口为 `/home/ningyd/datasets/BIGsmall/reports/industryshapes_real/index.html`。

实际原件的 0 值像素总数为 36,981,209，65535 值为 1,571,090，370 帧均有 65535。非零且小于 65535 的像素比例均值为 66.08%，帧间范围 26.41%–90.28%；这是原值统计，不能直接命名为几何有效率。

本轮只选 classic，其 `depth_scale` 均为 1.0，避免 extended 导出卡关于比例换算的歧义。原始深度值 0 和 65535 分别计数；65535 仅在显示时排除，来源未明确的物理有效性不能由本工具补造。形状相同不单独证明 RGB／深度像素配准，未运行点云投影或几何精度验收。此数据提供物体位姿，不提供机器人电机动作或原生抓取候选标签。
