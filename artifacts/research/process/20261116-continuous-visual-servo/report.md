# 连续视觉伺服仿真实现与验证

工作开始于 2026-11-16，最终验证于 2026-11-17（Asia/Shanghai）。修改前基线为 `a4acea8ddb95c93eaedc873e12e92f051f473420`。用户确认先完成仿真与逐帧相机外参支持；本轮没有真实付费模型调用、硬件动作或公开推送。依照当前 AGENTS.md，由当前模型实施，没有生成或冒用 Astra 计划。

## 已实现

运动技能内部持续采集配对 RGBD，由 OpenCV 更新当前目标，再经过动态 SafetyShield 检查和受限关节控制。Sol/Molmo 的初始规划与目标提名职责保留，高频环不调用模型。默认物理 240 Hz、视觉 30 Hz、关节指令 48 Hz；控制状态在更新目标时连续保留。

顶视相机可以在世界坐标中平移；RGB、depth、当前外参与标定版本一起绑定。缺失、过期、未来、倒序或重复帧，以及目标跳变、超时、安全拒绝均停止并 hold。LIFT 接触保持阶段仍持续采样；POST 使用最新观测和实际检查过的终点。完整源码核验保留在技能边界，帧前后继续核验当前租约、attempt、取消与期限。

此版本支持注册场景中的位置伺服和顶视平移。相机旋转、变焦、自动最佳视点规划、真实可移动相机接入与真机实时性尚未验证。原手指轨迹和最低高度等安全规则保持有效。

使用方式见 [连续视觉伺服说明](../../../../docs/research/continuous-visual-servo.md)。零模型验证命令：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/verify_visual_servo.py \
  --output experiments/results/phase9/visual-servo-new-run
```

## 独立伺服开发验证

真实 MuJoCo 渲染、OpenCV 测量与执行器运动；初始提名使用显式 RGB 颜色测试夹具。固定 seed 31 的四个预先声明用例全部通过。前三例同时要求控制残差与独立物理水平误差不超过 5 mm。

| 用例 | 新鲜反馈数 | 仿真视觉 Hz | 墙钟反馈 Hz | 控制残差 mm | 独立水平误差 mm |
| --- | ---: | ---: | ---: | ---: | ---: |
| 固定相机 | 93 | 30 | 30.76 | 2.807 | 2.943 |
| 运动中移动相机 | 93 | 30 | 29.51 | 1.307 | 2.472 |
| 外力驱动目标移动 | 95 | 30 | 30.50 | 1.454 | 2.311 |
| 相机移出视野 | 7 | 30 | 29.67 | — | — |

相机实际平移 53.85 mm；外力使目标实际移动 12.64 mm，控制不读取该独立物理证据。丢失在物理步 176 注入，同一步检测并 hold，之后关节指令数为 0；上一有效观测为步 168，检测间隔为 8 步，即 33.3 ms 仿真时间。单次采样与 IK 最长为 37.21 ms。墙钟结果是本机一次测量，不构成硬实时保证。

[协议](validation-protocol.json) 固定源码、资产和运行库版本；[结果](validation-summary.json)、[复核](verification.json) 和 [raw 清单](raw-manifest.json) 随代码保留。独立重建校验了全部 297 帧 RGB、原始 depth、有效掩码、逐帧标定与观测校验和，1210 个原始文件保存在本地忽略目录：

`experiments/results/phase9/visual-servo-20261116/validation-final-01`

这四例是开发验证，不是新 seed 泛化批次、完整抓放成功率或正式研究验收。

## 完整 worker 集成的实际边界

真实 SQLite、worker、MuJoCo 和 SafetyShield 运行，云端及 Molmo 由软件协议替身提供；5 次软件模型协议请求对应 0 次真实付费调用。

- MOVE_ABOVE：92 次反馈，墙钟 21.78 Hz，控制残差 1.721 mm，成功。
- APPROACH：53 次反馈，墙钟 21.74 Hz，控制残差 3.535 mm，成功。
- GRASP：原手指控制执行成功，有双侧接触证据。
- LIFT：第二次动态检查被 `MIN_HEIGHT` 拒绝；TCP 高度约 0.048 m，规则下限为 0.080 m。现有向上脱离例外要求目标 x/y 与当前 TCP 完全相等；固定终点经过第一段物理步进后不再满足该条件。控制 hold，没有修改安全规则来继续动作。

完整抓放 `physical_success=false`，终止原因为 `SAFETY_SHIELD_SERVO_REJECTED_OR_LIMITED`。本轮 worker 测试通过验证的是显式接入、前两次运动收敛、动态安全检查和原始帧归档，不能据此宣布完整任务成功。后续需要在原安全边界内单独处理低位垂直抬升与逐帧检查的兼容性。

147 次动态检查均对应已归档原始观测，150 帧（包括技能参考帧）已重建并通过校验和验证。见 [worker 摘要](worker-summary.json) 和 [原始文件清单](worker-raw-manifest.json)。原件保存在本地：

`experiments/results/phase9/visual-servo-20261116/worker-final-01`

包含数据库/安全核验/证据归档的 worker 吞吐低于独立伺服验证，应分别报告。

## 软件核验与失败记录

相关回归最终为 **422 passed、1 failed**，用时 137.66 s。唯一失败：

`test_actual_worker_cloud_image_route_preserves_geometry_and_one_request_budget[43001-development-CANDIDATE-False]`

该测试预期 `executed_actions == 0`，实际为 8；在基线源码的独立副本中复跑得到相同失败（1 failed、6 deselected）。保留 [最终回归](related-regression.log)、[首次回归](initial-related-regression.log) 和 [基线复跑](baseline-fallback.log)。没有改写其预期，也没有宣称相关回归或全仓库全部通过。本轮未重跑全仓库 pytest。

[静态核验](static-validation.log) 中 Ruff 对 15 个文件通过，mypy 对 9 个源码/CLI 文件通过。独立设计与代码审查已完成；审查指出的未来帧、参考帧重用、丢失验证假阳性、raw 缺失，以及 LIFT 保持期缺采样均已修复并验证。实际接触保持测试覆盖完整 0.5 s 中的 15 次反馈。`git diff --check` 通过。

早期失败版本保留于 `experiments/results/phase9/visual-servo-20261116/attempts/v1|v2|v3`，没有覆盖原始实验。包括混用几何测量引起的跳变、验证驱动初始点与几何中心不一致，以及较弱的丢失验证条件。初次 worker 超过 100 ms 的采样失败也保留；分段计时定位到高频环重复全量源码哈希，改为原有技能边界核验后，完整 worker 最大成功采样耗时为 47.47 ms。

本地复核命令（仅读取已有证据）：

```bash
.venv/bin/python artifacts/research/process/20261116-continuous-visual-servo/recheck_evidence.py
```

[合并复核结果](evidence-recheck.json)：1880 个原始文件指纹匹配，447 帧 RGBD 重建校验通过，四项开发门槛通过，147 次动态检查均有 raw；同时保留 worker 完整任务失败结论。

所有 raw 及数据库按既有交付边界管理，Git 中清单与派生结果不是完整远端复现包。正式研究状态为 `NOT_ACCEPTED`，native action 资格未授予，qualified groups 未增加。
