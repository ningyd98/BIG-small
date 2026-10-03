# T2 同步 RGB-D 采集报告

状态：实现与局部验收完成；未提交、未推送，未改 `scene.xml`。

## 接口与行为

- `MuJoCoCaptureSession(config)` 是上下文管理器；`capture()` 每次真实渲染生成新 `RGBDObservation`，`capture_with_instances()` 返回 `CapturedFrame`。会话复用 reset 时创建的同一个 Renderer，退出时关闭。
- `CapturedFrame` 含 observation、行优先扁平化的 `instance_ids`、`instance_labels`、物理状态 hash 和每个 pass 的状态 hash。`instance_ids` 是 MuJoCo **geom ID**，`-1` 为背景；这些字段只用于离线标注，不进入在线 `RGBDObservation`。当前单块体可直接作为实例；未来多 geom 物体需要按 body/对象合并。
- camera 对同一物理状态执行 RGB、米制深度和实例分割渲染；每 pass 后以及标定完成前重新计算状态 hash，任何变化直接抛错，不返回混合帧。无仿真步进。原始 float32 光轴深度、有效掩码、行优先 4×4 相机到世界变换和内参随帧保存。
- `SensorFrame` 新元数据有兼容默认值。旧 `RGBDObservation` 输入自动以 `frame_id` 填充 `observation_id`，自动推导深度有效掩码与完整性校验和；缺少 scene/episode/标定版本时保持 `None`，表示**未绑定研究场景**，不伪造身份。新 MuJoCo 帧三者均有值。校验和覆盖观测身份、时刻、仿真时间、来源、深度约定、场景/episode/标定、尺寸、内外参和 RGB/深度/掩码摘要。历史帧可反序列化；在线过期拒绝仍由现有规划入口处理。`crop()` 保留原 `observation_id` 并重算内容校验和，不假装新采集。

## TDD 与验证

首次 RED：`MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_observations.py tests/test_rgbd_capture_session.py` 得到 **5 failed, 10 passed**，失败点是 observation_id 和会话接口缺失。随后 artifact bundle 新测试 RED 为 **1 failed, 15 passed**（缺 `save_captured_frame`）；采集时刻/来源篡改反例 RED 为 **1 failed**（原校验和未覆盖）。对应 GREEN 后，完整相关回归命令：

```bash
MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_observations.py tests/test_rgbd_capture_session.py tests/test_phase9_mujoco_load.py tests/test_phase9_mujoco_physics_step.py tests/test_rgbd_isaac_transport.py tests/test_rgbd_planning.py
```

结果 **25 passed, 1 warning, 2.29s**；唯一 warning 为 Starlette 对 AnyIO `BlockingPortal` 别名的弃用提示。日志见 `artifacts/research/process/20261003-phase1/capture/pytest-rgbd-phase9.log`。覆盖连续帧身份、三 pass 同状态、状态突变拒绝、独立平面反投影、Renderer 构造一次及正常/异常退出释放、非法深度/标定/掩码/校验和。

所改文件相关 `ruff check` 通过，明确列举的 7 个 source 文件 `mypy` 通过；日志分别为 `capture/ruff.log`、`capture/mypy.log`。扩展到整个 `vision` 包时，`planner.py` 原有 3 处 mypy 错误仍在本任务边界外，未改该文件。

## 实际采集证据

运行：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/verify_rgbd_capture.py
```

证据目录 `artifacts/research/process/20261003-phase1/capture/` 含 `rgb.png`、原始 `depth.f32`、`valid_mask.u8`、`instance_geom_ids.i32`、`depth.png`（仅可视化）、`observation.json`、`measurement.json`、`capture-run.log`。`measurement.json` 记录各文件 SHA-256、标定版本、帧/episode/scene ID、三 pass hash 和 Renderer 关闭结果。以 `scene.xml` 中 table 顶面独立几何值 **z=0 m** 为参考，在 36,300 个有效桌面像素中采样 100 点，反投影最大绝对误差 **0.002728 m**、平均 **0.000794 m**，均低于 0.005 m 验收阈值。三 pass hash 一致且 `renderer_closed_after_session=true`。

文件变更限于 `simulation/models.py`、`simulation/mujoco/{camera,backend}.py`、`vision/{observations,capture}.py`、`tests/test_rgbd_observations.py`、新增 `tests/test_rgbd_capture_session.py` 和 `scripts/verify_rgbd_capture.py`，以及上述证据与本报告。`simulation/config.py` 已有尺寸上限和默认 320×240，故未重复修改。
