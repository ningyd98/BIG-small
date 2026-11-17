# Grasp and Placement Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 修复连续视觉抓放的抬升阻断与途中持物丢失检测，并验证完整抓放。

**Architecture:** 显式、不可变的竖直脱离路径绑定实际目标及任务/步骤；上下文和控制循环共享约束。机器人运动适配器为持物动作安装每物理步守卫，所有异常退出 hold。完整 worker 接入保持动态目标与 SafetyShield 一致。

**Tech Stack:** Python、MuJoCo、OpenCV、pytest。

**Spec:** docs/superpowers/specs/2026-11-17-grasp-place-repair-design.md

## Global Constraints

- 安全高度至少 80 mm，脱离路径横向偏差/回落各最多 1 mm；无显式路径时保留原严格规则。
- 视觉 30 Hz 仿真周期、关节指令固定网格和原速度/加速度边界继续有效。
- 物理评分要求物体抬升至少 50 mm、保持 0.5 s、放置稳定 1 s；在线控制不读取物体真值。
- 保留手指轨迹、预算、原始证据；零真实付费模型、零硬件、本地提交，公开推送继续暂缓。

## Review Focus

- 路径被复用到另一 task/step、目标被回调改变、低位横移假装竖直脱离时必须拒绝。
- 中途掉物发生在两次视觉采样之间，也要在下一条关节命令前 hold。
- 传入路径或持物约束不得从模型参数中自动获得；角色源码和上下文都需绑定。
- 后续 PLACE/RETREAT 在低位开始时不得通过放宽高度或历史几何绕过安全检查。
- 验收依据物体实际抬升和稳定落位，不能只有 TCP 收敛、双侧接触或 pytest 通过。

### Task 1: 显式脱离路径与预期持物上下文

**Files:** Create `edge/safety/clearance.py` under `src/cloud_edge_robot_arm`; Modify safety `models.py`, `context_builder.py`, `rules.py`; Create `tests/test_servo_grasp_safety.py`。

**Interfaces:** `VerticalClearancePath(task_id, step_id, skill, start_m, target_m, minimum_height_m)` validates immutable vertical intent and measured corridor; `SafetyContextBuilder.build(..., vertical_clearance=None, expected_holding_object_id=None)` binds trusted execution context, not model parameters.

- [x] 写低位微小偏差、有界路径、身份/目标不匹配和无持物拒绝的测试；运行并观察 RED。
- [x] 实现路径和上下文绑定；原无路径低位横移仍拒绝；运行测试，Expected: PASS。

### Task 2: 每步运动守卫及完整抓放接入

**Files:** Modify MuJoCo `motion_controller.py`, `visual_servo.py`, `skill_robot.py`; Modify `research/sol_molmo_components.py`, `vision/molmo_worker.py`; Test `test_visual_servo_control.py`, `test_rgbd_physical_skills.py`, `test_sol_molmo_worker_integration.py`。

**Interfaces:** Motion controllers accept optional `state_guard: Callable[[], None]`, execute it before commands and after each physics step, hold on exceptions. Visual session carries the bound clearance path. Skill adapter preserves its active guard through LIFT contact hold. Component safety receives the same path and expected object as the actual motion.

- [x] 将 worker 伺服用例加强为要求独立物理成功，运行观察原 MIN_HEIGHT 失败；为真实物理中途丢失与路径越界写失败测试。
- [x] 实现每步守卫、低位路径绑定、精确目标核验及源码哈希绑定；Expected: 低位 LIFT 成功，违规/掉物及时 hold。
- [x] 逐个定位完整抓放后续实际失败；每个修复先写失败测试，不扩大边界；Expected: 完整 worker 独立物理成功且末端标记可复核。

### Task 3: 回归、独立验证与交付

**Files:** Update usage docs; Create bounded process report and manifests under `artifacts/research/process/20261117-grasp-place-repair`。

- [x] 串行重复完整 worker 与四项独立视觉用例；保存成功与失败原件、物理指标及墙钟频率，校验 RGBD/标定/源码。
- [x] 运行相关测试、全仓库 pytest、Ruff/mypy，列出所有实际失败及基线归属。
- [x] 进行一次独立代码审查，修复可操作问题并验证，提交本地研发分支。

Expected: 报告区分模型替身开发验证、完整仿真物理结果和未授予的正式/真机资格；不以软件绿灯替代物理成功。

实际完成边界：整库 7,088 项分段核对保留 3 failed、1 error、9 未完成，其中一项本轮 LIFT 可见性问题随后修复。当前树收集 7,089 项；最后组件相机阶段修复后重新运行 220 项相关回归及三次完整 worker，未再重跑整库。一次最终审查的两项 Important 经 RED→GREEN 验证；无延后 Minor。详见 `artifacts/research/process/20261117-grasp-place-repair/report.md`。本地提交，公开推送继续暂缓。
