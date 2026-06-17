# Phase 10.2B 控制台差距记录

这份记录用于说明控制台动手前仓库还缺什么。结论很直接：后端已有规划、监督、风险、事件和验收脚本，但还没有一个给浏览器读取的安全汇总层；前端也还没有独立控制台。Phase 10.2B 要补的是“查看和验收工作台”，不是远程操控机械臂。

## 现有基础

- `src/cloud_edge_robot_arm/cloud/api/app.py` 已经提供规划、监督、风险、Skill Cache、AUTO 和事件接口。
- `src/cloud_edge_robot_arm/experiments/` 里有实验配置、profile、指标和批量运行能力，可作为软件实验的来源。
- `src/cloud_edge_robot_arm/real_robot/` 里已有 Phase 10 配置门禁、硬件执行门、dry-run 证据、操作员确认、分级验收和溯源模型。
- `scripts/verify_project.py`、`scripts/verify_phase10_0.py`、`scripts/verify_phase10_1.py`、`scripts/verify_phase10_2a.py` 是当前软件侧验收入口。

这些能力不能直接暴露给浏览器。控制台需要的是整理后的状态、证据和门禁结果。

## 后端读模型缺口

当时还没有 `dashboard` 后端包，也没有统一的 `DashboardSummary`。如果前端直接读 artifact 或拼多个旧接口，就会把安全状态解释逻辑散到浏览器里。这不适合展示真实硬件边界。

需要补的读模型包括：

- 项目状态、真实机械臂验收状态、最高硬件级别和硬件声明。
- 服务健康、阻塞原因、证据列表和安全门快照。
- 明确的 `hardware_motion_authorized=false`，而不是让 UI 自己推断。

## 实时事件缺口

原 API 没有控制台专用的 WebSocket 流。控制台至少需要单调递增序号、心跳、按序号回放，以及轮询兜底。慢客户端保护可以后续加强，但事件模型一开始就要能审计，不能只靠页面刷新。

## 软件实验入口缺口

已有实验工具偏批处理，不适合直接给页面按钮调用。控制台启动实验时必须走后端 allowlist：

- 不接收 shell 命令、脚本路径、可执行文件、环境变量或任意文件路径。
- 只允许声明过的软件实验类型。
- 写操作默认关闭，开启也不能出现真实硬件写入能力。

## 证据索引缺口

artifact 已在磁盘上，但缺少安全索引层。浏览器读取证据前需要处理：

- 拒绝路径穿越。
- 跳过逃逸 artifact 根目录的符号链接。
- 控制文件大小和扩展名。
- 返回前做脱敏，至少覆盖 token、password、secret、controller address 和 robot serial。

## 前端页面缺口

当时仓库没有 `dashboard/` 前端。Phase 10.2B 需要的首批页面是：

- 概览。
- 仿真实验。
- 任务执行只读页。
- 安全验收。
- 证据浏览。
- 指标对比。
- 审计事件。
- 404 页面。

共用组件包括环境横幅、状态标签、安全门卡片、阻塞列表、溯源卡片、时间线和 JSON 查看器。页面文字要直接说明状态，不靠颜色传达安全结论。

## 安全边界

浏览器不能直连 ROS 2 topic/action、MoveIt execute、`ros2_control`、厂商 SDK 或真实控制器地址。后端 capabilities 在 Phase 10.2B 必须返回空的硬件写操作列表。

真实硬件状态保持：

- `real_robot_validation=NOT_STARTED`
- `highest_acceptance_level=NONE`
- `hardware_claim=PLANNING_ONLY`

控制台不能让硬件运动变得可能。

## 不在本期改动范围

- 不改 SafetyShield 的判定语义。
- 不放宽 HardwareExecutionGate。
- 不改 PCSC、ETEAC、AUTO 的运行逻辑。
- 不重写 Phase 8、Phase 9、Phase 10 已验收运行证据。
- 不新增真实控制器连接，也不新增真实机械臂运动路径。
