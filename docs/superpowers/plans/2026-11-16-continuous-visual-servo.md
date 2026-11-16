# Continuous Visual Servo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 在 MuJoCo 动作内部持续使用 OpenCV RGBD 更新控制目标，支持平移顶视相机。

**Architecture:** 独立视觉提供器负责逐帧坐标和身份验证；独立伺服控制器通过既有执行器和限幅更新轨迹。显式技能会话与组件角色绑定负责接入，旧模式保持原义。

**Tech Stack:** Python、OpenCV、NumPy、MuJoCo、pytest。

**Spec:** docs/superpowers/specs/2026-11-16-continuous-visual-servo-design.md

## Global Constraints

- 默认视觉周期 1/30 s，关节控制约 0.02 s，物理周期 1/240 s；记录仿真与墙钟频率。
- 最大帧年龄/间隔 0.1 s、单帧位移 0.01 m、初始目标校正半径 0.05 m。
- 保留所有硬停止、独立评分、冻结原件；不改变手指指令，不启动付费模型批次，不公开推送。
- 本次支持顶视平移与逐帧外参，真机和主动视点规划另行验证。

## Review Focus

- 同一图像配上旧外参/标定版本不能被误认为目标移动。
- 缺帧、重复、未来时间戳和计算超时应停止，不能复用旧坐标。
- 目标移动时不能重置速度状态并产生加速度跳变。
- 动态目标与 SafetyShield 实际检查目标必须一致。
- 会话异常退出后普通运动不得复用视觉回调。

### Task 1: 每帧几何与相机平移

**Files:** Create `src/cloud_edge_robot_arm/vision/servo.py`; Modify `src/cloud_edge_robot_arm/simulation/mujoco/backend.py`; Test `tests/test_visual_servo.py`。

**Interfaces:** `OpenCVServoFeedback(reference, tracker, evidence, *, skill, initial_target, marker_family_id=None)` consumes RGBD and returns current Pose via `update(observation)`; `set_camera_position(position_m)` moves the world-attached top-down camera without stepping physics.

- [x] 写并运行相机平移坐标一致、坏帧拒绝、完整当前几何及旧跟踪器绑定未放宽的失败测试。
- [x] 实现逐帧反馈、平移相机接口与必要审计；运行对应测试。

### Task 2: 连续关节运动与技能会话

**Files:** Create `src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py`; Modify `skill_robot.py`; Test `tests/test_visual_servo_control.py`。

**Interfaces:** `VisualServoConfig`, `VisualServoSession(sample, config)`, `MuJoCoVisualServoController(backend).move_tcp(target, timeout_s, session=..., max_joint_velocity_rad_s=..., max_joint_acceleration_rad_s2=...)`; robot context manager `visual_servo(session)` selects it.

- [x] 写并运行同次运动内改目标、丢失立即 hold、速度/加速度及会话清理的失败测试。
- [x] 实现采样期限、持续轨迹状态、新鲜样本收敛和异常 hold；运行真实物理测试与既有运动回归。

### Task 3: 组件接入与验证记录

**Files:** Modify `research/sol_molmo_components.py`, `vision/molmo_worker.py`; Create `scripts/verify_visual_servo.py`, `docs/research/continuous-visual-servo.md`; Test component policy and integration.

**Interfaces:** `make_worker_binding(..., visual_servo=False, camera_position_m=None)` binds policy; matching job parameters select it. Every refreshed dynamic target passes a fresh SafetyShield context before actuator submission.

- [x] 写并运行角色/job 不一致及动态安全目标绑定的失败测试。
- [x] 接入逐帧反馈、目标安全核验、审计与配置；保留旧路径。
- [x] 运行本地真实 MuJoCo 固定/移动相机、扰动跟随和丢失停止开发验证；保存频率、误差与原始证据指纹。
- [x] 运行相关回归、Ruff/mypy、独立代码审查；修复发现后记录范围并提交本地研发分支。

最终记录：`artifacts/research/process/20261116-continuous-visual-servo/report.md`。四项开发验证通过；相关回归 422 passed、1 项基线既有失败。完整 worker 前两项运动收敛，但 LIFT 被 MIN_HEIGHT 拒绝，未完成抓放；真机与泛化均未验收。
