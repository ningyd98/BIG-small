# 新增真实 RGBD 数据读取器与离线接入

> 使用 executing-plans 在当前已授权工作区连续实施；不提交、不推送，保留已有改动。

**目标：** 将已下载的 IndustryShapes 370 对、MicroAGI01 open-source-12、VINS Handheld/Normal 接入统一索引、CPU 批量读取、预览和离线回放。

**设计依据：** `docs/superpowers/specs/2026-10-03-external-rgbd-deployment-design.md` 的数据契约和验收要求；用户后续“增加数据集”“完整下载”“继续下一阶段开发”扩展了原有两套数据的范围。本阶段复用同一架构，不代表主研究路线 T3/T4 已完成。

**约束：** 本阶段从已下载且固定摘要的文件离线转换，不发起网络请求。原文件不改写；派生内容写入外部数据目录。官方 test 不变成 train；未知划分保持未知。保留 uint16、原始时间戳、原生分辨率和来源摘要。不猜内参、量纲、同步、动作或执行成功。RGB8 深度可视化不能作为数值深度。65535 采用明确记录的保守排除策略，不宣称上游定义了无效哨兵。

**接口：** 原生源适配器 → 有摘要及完成标记的逐帧派生记录 → DatasetSample → DatasetLoader / DatasetObservationProvider。使用现有 CLI 的 plan/extract/validate/index/preview/smoke/deploy。新增数据源的 download 仅核验已有固定文件，缺文件时报错，不能偷偷改用其他网络通道。

### Task 1: 统一派生记录与像素有效性

- 先编写测试：深度无损、显式排除值、未知量纲、源/记录身份校验、路径与摘要篡改、GT 与模型输入分离。
- 运行测试确认失败；实现逐帧记录读取、时间配对辅助函数以及显式有效性策略。
- Expected: 新测试全部通过，既有 external RGBD 测试仍通过。

### Task 2: 三套原生源转换

- 先编写小型真实格式夹具测试：Industry 官方 test 与标定；MCAP protobuf/zstd 与单位；ROS1 bag bz2、精确 header 时间配对、排除伪深度；损坏格式失败。
- 运行测试确认失败；实现有资源上限的解析和逐帧转换。按时间一对一配对，保存未配对清单；不捏造时间和帧率。
- 固定 manifest 和源摘要，原子生成派生记录及 inventory；再次运行验证并复用。
- Expected: 夹具测试全部通过；真实文件得到可检查的配对数量与限制。

### Task 3: CLI 与真实验收

- 先补集成测试：新增源 CLI、缺文件/摘要不符/残缺转换失败、索引与划分、单轨迹多帧预览、worker 0/2 和回放隔离。
- 集成现有部署流程。新数据只验收已选范围，不能冒充整个上游数据集或完整机器人轨迹。
- 对三套真实文件完整转换、全帧解码/校验、索引、预览、CPU 0/2 smoke 和重复部署；保存实际报告。
- Expected: 每套选定范围通过，未配对帧和能力缺口可追溯；Industry 370 对全部保持 test。

### Task 4: 回归、审查与文档

- 运行 external RGBD 及相关回归、Ruff、mypy；修复本次引入的问题。
- 按 executing-plans 要求进行一次独立最终审查；重要问题补 RED/GREEN 测试并修复。
- 更新快速使用文档、权威状态与实际验收报告；不改变 T3/T4 READY 状态。
- Expected: 可用入口、真实计数、限制和测试证据齐备。

## 执行结果

2026-10-03，Task 1—4 已完成。三套新增源共 1,451 对通过真实验收；269 项数据测试及 172 项旧路径回归通过。一次独立最终审查发现的重复部署空间门禁问题已修复并定向复核通过。证据见 `artifacts/research/process/20261003-additional-rgbd-readers/acceptance.md` 与同目录进度记录。保留当前工作区，不自动提交或推送；研究路线 T3/T4 仍为 READY。
