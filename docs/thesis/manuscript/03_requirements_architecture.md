# 第三章 需求分析与总体架构

## 3.1 功能与非功能需求

系统需要支持任务规划、契约验证、协同模式选择、边缘执行、安全拒绝、故障恢复、局部重规划、实验运行、指标分析和证据导出。非功能需求包括实时性、安全性、可恢复性、可复现性、可审计性和环境阻塞可见性。

## 3.2 总体架构

系统由云端规划层、边缘运行层、仿真与 dry-run 层、Dashboard 与模型控制层、证据与验证层组成。云端 API 基于 FastAPI；边缘端包含任务状态机、SafetyShield、技能执行器和事件检测器；实验层包含 Phase 8 runner、MuJoCo、Isaac 环境检查、MoveIt dry-run、Phase 11 Simulation Runtime 和 Phase 11.2 Planner Dry-Run。

## 3.3 安全边界

Dashboard 不直接控制机械臂；planner dry-run 使用 `dispatch=false`；真实硬件写操作为空。当前 evidence 明确 real_controller_contacted=False，hardware_motion_observed=False，hardware_write_operations=[]，highest_real_hardware_acceptance_level=NONE。

