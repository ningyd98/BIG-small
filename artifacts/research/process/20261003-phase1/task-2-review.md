# T2 独立审查：同步 RGB-D 与连续 MuJoCo 相机会话

审查日期：2026-10-03。结论：**ready（就 T2 代码与已存采集证据放行）**。

## 范围和方法

读取 T2 brief/report、研究规格 §4.1 和相关真实性要求、执行计划 T1/T2 与阶段边界；审查 observations/capture、simulation models/config、MuJoCo camera/backend、两份 RGB-D 测试及 verify_rgbd_capture.py。用 `.superpowers/sdd/2026-10-03-rgbd-evidence-research-roadmap/before/` 对照本轮已有文件变更，没有把 `git diff HEAD` 当作任务范围。读取 T1 模型、来源审计实现与已修复审查报告，只核对采集输出的集成边界。

未修改产品或测试文件，未提交、切分支、调用 GPU 或重跑整套测试。根代理正在运行的阶段合并回归不属于本报告独立执行结果；尚未审查最终收尾过程文档。

## 规格符合性

本次限定配置与 T2 要求相符：

- `simulation/mujoco/camera.py:83` 起对同一 `update_scene` 结果依次渲染 RGB、光轴米制深度和实例图；采集路径没有物理步进，状态摘要含 sim_time、qpos、qvel、act、ctrl，并在准备场景、每个 pass 和标定收尾检查变化。已有突变测试在 RGB pass 后改变 qpos，要求抛错且会话释放。
- `camera.py:128` 将 MuJoCo 相机轴转换到 optical 坐标，保留内参、行优先 camera_to_world、有效掩码和标定版本；每次采集产生 UUID 帧号。`simulation/mujoco/backend.py:132` 为每次 reset 分配 episode ID，连续采集沿用同一 episode。
- `vision/observations.py:43` 校验载荷、尺寸、有限深度、掩码、齐次刚体变换及校验和；零深度不能给出 Pose。校验和覆盖时刻、来源、身份、标定及 RGB/depth/mask 内容。`observations.py:127` 的 crop 保留观测身份并调整内参、重算内容校验和。
- `vision/capture.py:31` 的上下文管理负责 Renderer 复用和正常/异常退出释放；实例图位于离线 `CapturedFrame` 中，不在在线 `RGBDObservation` 字段内。
- 历史帧可以恢复，在线过期检查仍由既有 `cloud/planning/pipeline.py:73` 执行。旧输入未伪造 scene/episode/calibration 绑定；真实 MuJoCo 帧均含这三项。

与 T1 的边界成立：T2 输出的观测校验和可作为 `RunProvenance.observation_hashes` 的来源；采集产物未被计为完成推理或动作，更未生成物理任务成功记录。保存的 observation.json 明确 `model_image_count=0`。没有重开 T1 已关闭的三项来源审计问题。

## 代码质量

实现集中在现有相机/观测边界，兼容旧 SensorFrame 默认字段，几何校验和身份管理明确。新增测试覆盖同步、连续帧身份、实例图隔离、Renderer 构造计数及异常释放。未发现需要架构重写或阻碍本阶段验收的代码质量问题。

## 独立证据核验

本审查仅执行 CPU 读取与复算：

- 对 measurement.json 所列 6 个文件重算 SHA-256，全部一致。
- 从 rgb.png、depth.f32、valid_mask.u8 和 observation.json 重建 RGBDObservation，现存 checksum 验证通过；JSON 往返保留校验和。
- 依据 scene.xml 桌面顶面独立值 z=0，读取原始深度和标定直接计算世界 z。在 36,300 个有效桌面像素中按脚本规则采样 100 点，最大绝对误差 **0.0027281284332274502 m**、平均 **0.0007935903072357231 m**，与存档一致且小于 5 mm。
- 检查偏离主点的 crop，裁剪像素与对应原图像素返回相同世界坐标并保留 observation_id。

另读取实施者日志：相关回归 25 passed；Ruff 通过；列举的 7 个 source 文件 mypy 通过。这些是存档结果，并非本审查重新执行。Renderer 关闭与三 pass 一致性由已有真实测试、代码及 measurement.json 共同支持。

## 问题分级

- **Critical：无。**
- **Important：无。**
- **Minor：无影响本阶段验收的实质问题。**

## 考虑后排除的行为

- 同一静止场景连续帧 sim_time 相同：符合不推进物理要求，新 UUID 与采集时间区分真实重采集。
- crop 后主点可以位于图像外：属于合法裁剪内参，不能沿用原来的“主点必须在当前图像内”限制。
- 实例 ID 是 geom ID 而非多 geom 物体的统一对象 ID：当前单块体配置满足 T2，约定已明示；后续数据工厂的对象聚合不在此次验收内。
- 原子落盘、批次 manifest、任意场景/模型并发修改支持及动作闭环：属于后续任务或当前公开会话接口之外，不作为 T2 缺陷提出。
- `simulation/config.py` 无本轮改动：现有尺寸上限和默认 320×240 已满足需求。
- 既有默认深度噪声、planner.py 的三处 mypy 错误：不是本轮新增问题；本次真实平面测量已包含当前噪声。
- 5 mm 桌面反投影证据：仅支持 T2 相机几何验收，不能替代目标定位 P90 与物理抓放成功率，未据此宣称完整 G1。

## 最终过程文档局部核对（2026-10-03）

按根代理请求，补读 `docs/research/process/` 全部七份文档、执行计划的当前状态及 Task 1/Task 2、`docs/current_authoritative_status.md` 和 `phase1-report.json`。本轮仅做文档一致性检查，未重审代码、运行测试或重复链接检查。

**结论：未发现确定的实质问题，P1 文档交接可用。**

- 完成范围一致为 P1 的 T1/T2；P2 的 T6a/T3/T4 仅就绪且尚未执行。没有把 P2、完整 G1 或 G2—G5 标为完成。
- 执行计划、阶段进度、交接和机器报告均使用 T1/T2 DONE、T6a/T3/T4 READY。验证矩阵的 T3 等行仍为 TODO，开头明确将其定义为“未取得本轮验收证据”；这是验证结果状态，不等同于任务依赖就绪状态，不构成完成或启动声明冲突。
- 15 项来源审计、T1 局部合并 35 项、T2 局部 25 项、P1 合并 65 passed / 1 warning、39.16 秒和 mypy 10 个 source 文件的口径分明，与本轮报告及根代理提供的最终结果相符。2.728 mm 最大值、0.794 mm 均值、100 个采样点和 36,300 个有效桌面像素与既审原始测量一致。
- 新正式运行数和权威论文运行数均为 0；旧 5,580 行保持排除，PHASE12_REJECTED 保留。真实 VLM 与研究物理任务执行未被软件/采集验收冒充。
- 交接包含下一入口、SceneSpec 的先后依赖、共享 backend.py 单写者、GPU 串行、未提交工作区保护、模型阻塞分支、geom 实例约定及已知检查边界；未发现妨碍下一阶段接续的关键缺口。

本节补充了首轮报告中“尚未审查最终收尾过程文档”的范围说明；产品代码审查结论仍为 ready。链接检查由根代理执行，本节不代替该结果。

## Post-freeze 差异复审（2026-10-03）

根代理在最终源码摘要核对时发现冻结后变更，变更来源尚未确认；本次保留现有内容，仅审查 `post-freeze-changes.patch` 所涉及的 observations.py、MuJoCo camera.py 及两份 RGB-D 测试。已通读这两份测试，包含可能早于旧 manifest 的缺采集时刻、历史时刻保留及异常载荷测试；未以 patch 中是否出现新增测试判断其是否已覆盖。为确认兼容性，仅只读核对 Isaac SensorFrame 解析和现有编码路径，未重新审查其余实现。

**差异审查结论：ready，未发现 Critical、Important 或实质 Minor。** 该结论是当前四文件的代码审查放行；旧 65 项结果不自动覆盖新内容，最终验收以根代理重新运行合并回归、真实采集、静态检查并核对运行前后摘要的结果为准。本复审没有调用 GPU、执行测试或修改产品代码。

- `vision/observations.py:218` 拒绝缺失 captured_at，传递原始采集时间，不再用转换时刻替代未知采集时刻。带真实历史时间的旧 SensorFrame 仍可恢复、裁剪和 JSON 往返，且保留其原始时刻；缺时刻的输入被拒绝是时效真实性要求，不属于应保留的正常兼容行为。
- `observations.py:220` 起在 PIL 分配与编码之前限制整数尺寸，并严格核对 RGB 三通道字节数和深度元素数。短载荷、超长载荷、非法尺寸均不能先进入 Image.frombytes；现有 tests 全文提供对应失败断言及编码路径不得触发的哨兵。
- 正常 MuJoCo 帧使用配置中的 Python int 尺寸、RGB bytes、完整深度 tuple 与有时区 captured_at，满足新边界。Isaac 的 `_parse_sensor_frame` 已返回 int 尺寸并校验 RGB/depth 长度，RGB 路径解析 captured_at；现有正常传输 fixture 和 standalone 编码结果均提供有时区时间。因此没有发现新增校验破坏正常 Isaac RGB-D 传输的情形。缺 RGB 的历史软件帧原本就不能转换为真实 RGBDObservation；新 scene/episode/calibration 字段仍保留兼容默认值。
- `simulation/mujoco/camera.py:83` 在开始采集时记录时间，三个 render pass 的耗时计入后续观测年龄。新增受控时钟测试让三个 pass 各增加 2 秒，断言返回的时刻仍是起点，避免渲染结束时把旧证据刷新为新证据。
- `camera.py:86` 起复制 cam_xpos、cam_xmat 和 cam_fovy；准备场景、每个 pass 后及最终封装前检查这些值，输出标定从初始副本构造。三项定向突变测试分别覆盖位置、仍为合法旋转的姿态变化和 fovy，并检查异常路径释放相机。此检查补足原物理状态摘要之外的标定变化边界。

本次实际读取的四文件 SHA-256：

| 文件 | SHA-256 |
|---|---|
| src/cloud_edge_robot_arm/vision/observations.py | `1114e6b2de4107ae516f12f8972fcb3b6f71eae7ae5a45bf93adfeb4aa673bb8` |
| src/cloud_edge_robot_arm/simulation/mujoco/camera.py | `ada89a381be96f8dc497dbcd5590503be115699b2ae0eec9d0970c12a63790ae` |
| tests/test_rgbd_observations.py | `333b1837cff77bdfce9344cf40f7617064570e1e3c08c881d6942316e9a250fe` |
| tests/test_rgbd_capture_session.py | `a1e858c5e5742b4c70b8a2b9959fa6f20f746a335eb226bfe63f74b030dff407` |

## 最后局部复审：深度转换参数（2026-10-03）

仅核对 camera.py 新增的 `vis.map.znear`、`vis.map.zfar`、`stat.extent` 初始值保存及 `check_calibration` 比较，以及当前六种标定突变的参数化测试。三个值均在开始渲染前转成独立 float 快照，任一变化沿用既有异常拒绝路径。测试在首个 RGB pass 后分别修改三个参数；extent 直接修改，znear/zfar 通过对应属性修改，并要求会话退出后释放相机。

**局部结论：ready；未发现新增实质问题。** 未展开其他问题域、未修改产品、未运行 GPU 或测试。最终回归与运行前后源码固定由根代理完成。

本次读取时的两个 SHA-256（取代上节这两个文件的旧摘要）：

| 文件 | SHA-256 |
|---|---|
| src/cloud_edge_robot_arm/simulation/mujoco/camera.py | `d85aa6eda7c9f658f2e3bb550c44b3462ebd65e290d5c7d9b79fa30639136e2f` |
| tests/test_rgbd_capture_session.py | `061f47285a8964a49e58e1033d8936ec3224da85ae5832ebbb58051c128743a0` |
