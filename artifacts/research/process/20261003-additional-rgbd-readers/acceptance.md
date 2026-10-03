# 新增真实 RGB-D 统一读取器验收

2026-10-03，在现有 `codex/ubuntu-integrated-deploy` 工作区完成。原始文件保持不变；本阶段从已有固定摘要文件离线转换，新增下载字节为 **0**。本报告只验收选定数据的读取与离线接口，不升级完整上游数据集或研究 T3/T4。

| 来源 | 实际有效 RGBD | 组数 / 预览帧 | 划分与时间 |
|---|---:|---:|---|
| IndustryShapes | 370 对，771 实例 | 6 场景 / 5 帧 | 全部官方 classic/test；无采集时间 |
| MicroAGI01 | 108 对 | 1 条观察序列 / 5 帧 | unknown split；10 ms 内最近日志时间一对一配对，最大差 4.918 ms，未确认采集同步 |
| VINS-RGBD | 973 对 | 1 条观察序列 / 5 帧 | unknown split；RGB/depth ROS header.stamp 精确一致；末尾 RGB 源帧号 973 未配对 |

合计 **1,451 对**。三套状态均为 `SELECTED_RGBD_VERIFIED`。详情见 [acceptance.json](acceptance.json)，再次验证入口为 [verify_acceptance.py](verify_acceptance.py)。

## 实际完成的验证

- 固定原件尺寸与摘要；转换前后均核验，逐帧派生记录与 PNG 另有摘要，原子完成标记覆盖派生清单。
- 全帧解码、数值有效性、索引与划分审计；RGB 为 uint8，数值深度为原始 uint16。
- 每套 CPU worker 0/2 smoke；另对首、中、末帧比较 RGB、原始深度及有效掩码，结果逐像素一致。
- 暂停、定位、恢复回放与原时间戳保留；普通模型观察无 GT/action，标注通过 oracle 通道读取。
- 三套重复部署均复用有效转换，仍执行原件/派生校验、质量检查与接口验收。[重复运行记录](repeat-verification.log)
- 15 帧预览生成，人工查看三套代表图，VINS 使用“原始深度/单位未核准”色条。MicroAGI 保留 RGB/深度不同原生分辨率；序列的 5 帧预览不冒充 5 个独立组。

## 软件验证

- 数据模块：**269 passed、2 skipped**。[日志](tests-external.log) 两项 skip 属于原完整 RoboMIND/GraspClutter 的显式真实数据门禁；三套新来源通过独立真实验收脚本验证。
- 旧 RGBD 采集、规划、运行时、数据生成/划分/导出与 GT 隔离路径：**172 passed**，1 条既有 Starlette 弃用警告。[日志](tests-regression.log)
- [Ruff](ruff.log) 通过；[mypy](mypy.log) 检查 19 个源文件通过，使用 `--ignore-missing-imports` 处理数据依赖缺失的类型存根。
- [独立最终审查](final-review.md) 通过，0 Critical、0 未解决 Important。审查发现的重复部署空间估算问题已补 RED/GREEN 测试修复：通过派生清单校验的成品不再重复预留首次转换峰值，最低空间余量仍生效。[定向修复验证](review-fix-tests.log)

扩展回归首次未设置仓库要求的 `MUJOCO_GL=egl`，在旧 MuJoCo Renderer 中止；保留 [原日志](tests-regression-no-egl.log)。按 `.env.example` 与既有验证矩阵设置 EGL 后，同一组测试完整通过，未修改仿真逻辑。

```bash
.venv-data/bin/python -m pytest -q tests/test_external_rgbd_*.py
MUJOCO_GL=egl .venv-data/bin/python -m pytest -q \
  tests/test_rgbd_*.py tests/test_phase9_ground_truth_isolation.py
.venv-data/bin/python \
  artifacts/research/process/20261003-additional-rgbd-readers/verify_acceptance.py
```

## 保留的能力缺口

Industry 原 test 的另外 553 帧缺镜像文件，未纳入 370 对选择。RGB 相机 K 和物体位姿可以读取，深度相机注册关系不作假定。MicroAGI 的日志时间不是已验证的采集同步，人体数据不是机器人控制命令。VINS 缺包内 CameraInfo 和已核准深度比例，`depth_m=None`；其 rgb8 深度可视化话题没有进入数值深度读取器。

三套均保留原始值，显式保守排除 65535 的数值有效掩码不等于物理测量精度认证；没有按猜测的距离阈值裁剪。当前均未通过点云几何、机器人基座标定或动作标签验收；没有训练模型、连接硬件或生成执行成功证据。原完整 RoboMIND/GraspClutter 阻塞状态不变。

统一命令、数据路径与 Python 示例见 [使用说明](../../../../docs/rgbd_additional_readers.md)。工作区未自动提交、合并或推送；实现文件摘要见 [code-manifest.json](code-manifest.json)。
