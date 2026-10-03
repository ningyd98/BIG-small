# 精选 RGB-D 接入最终复核

日期：2026-10-03。只读复核精选来源清单、读取器、原子发布、CLI 接入及验收门禁；未修改实现或原始数据。

结论：此前发现的问题均已关闭，本次范围内没有剩余必要修复。

- 标注门禁已关闭：`deployment.py:333` 合并 reader 的 `annotations.issues`，并把空实例列表及不可用 visible mask 计为标注不完整，避免错误升级验收。
- 来源身份已关闭：`deployment.py:219` 将 dataset、storage format、reader metadata 纳入部署身份；改变深度证据不能复用旧 raw 成品。
- 空间门禁已关闭：`fiftyone_curated.py:200` 在打开派生文件前检查完整 PNG／UTF-8 JSON 实际载荷与空闲保留量，每 1 MiB 块再次检查，写入 partial、flush/fsync 后原子替换；ENOSPC／EDQUOT 升级为 `BLOCKED_STORAGE`。`curated_deployment.py:80` 传入计划规定的保留量。存储中断不覆盖既有成品，空间不足时不截断既有 partial。

验证命令：`.venv-data/bin/python -m pytest -q tests/test_external_rgbd_curated.py tests/test_external_rgbd_curated_deployment.py`。结果：**45 passed in 0.78s**，覆盖空间不足、写入中空间变化、来源变更及标注缺失。

实际来源 schema 报告确认 10 个场景各有 4 种真实相机，共 40 个 RGB-D 记录；全部数值深度为 float32，RGB 与深度尺寸相同，669 个 mask crop 无 bbox 尺寸异常。毫米只转换一次为米；原始浮点深度保留，GT 独立于模型输入。

直接读取外部部署报告确认 `CURATED_RGBD_VERIFIED`、40 样本、10 场景、0 隔离、5 组预览及 0／2 worker CPU smoke 报告。40 个样本都有公制深度，几何能力计数仍为 0；内参、采集时间、机器人动作及官方 split 未补造。`original_full_target_verified=false`、`execution_verified=false`，精选验收没有升级为完整数据或真实执行验收。

实际部署证据：`/home/ningyd/datasets/BIGsmall/reports/graspclutter6d_curated/deployment.json`；来源证据：`artifacts/research/process/20261003-curated-rgbd/grasp-curated-schema-validation.json`。本次复核没有新增网络下载。
