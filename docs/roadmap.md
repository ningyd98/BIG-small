# 路线图

## 当前阶段

Phase 10.2A-R 主要整理仓库文档、项目结构说明、验证入口、CI 检查、变更记录和贡献规则。

## 后续阶段

- Phase 10.2B：实验与安全验收控制台。
- Phase 10.2C：真实机械臂 Level 0 只读验收。
- Phase 10.3：低速运动和真实任务实验。
- Phase 10.4：论文实验、专利材料和最终结果封存。

## Phase 10.2B 边界

Phase 10.2B 前端不是浏览器里的机器人遥控器。它可以通过 FastAPI/WebSocket API 展示实验状态、安全门、操作流程和证据浏览，但不能直接连接 ROS 2 trajectory、MoveIt execute 或真实控制器。
