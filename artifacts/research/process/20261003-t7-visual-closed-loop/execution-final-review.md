# T7 execution v2 最终独立审查

审查时间：2026-10-04 00:08 Asia/Shanghai（2026-10-03 16:08 UTC）。

结论：对下列哈希绑定的 `vision/execution.py` v2 temporal tracker、边界深度过滤、部分动作记录、初始急停、最短截止时间及 lift 稳定保持，**无未关闭 P1/P2 阻断项**。本次只读检查执行源码，未运行 GPU 或真实模型请求，未修改冻结 engine、CLI、T4/T5 代码或场景资产。

工作台独立语义尾评分接线不属于该 engine 通过结论：本次读取 worker 时仍以 `outcome.success` 写 `task_success`，root 尚需接入已完成的 `apply_s01_task_semantics` 并验证返回结果不会再次被覆盖。此前报告的 worker 错目标假成功问题不能仅凭 engine 审查通过而关闭。

## 审查结果

| 检查项 | 结果与证据 |
| --- | --- |
| 初始目标身份 | 初始目标与区域都要求唯一、足量的同色 RGB-D 支持。后续候选须在历史支持与已确认 TCP 位移预测范围内；新出现的范围外同色候选被拒绝。 |
| 时序碎片与遮挡 | 分裂支持只有在投影后的缺失像素中具有足够当前前景深度证据时被接受。零深度、同平面缺口、背景缺口均未被当作工具遮挡。 |
| 边界 RGB/深度混合 | 只排除色边缘单像素、与相邻可信支持具有明确深度跳变的异常点；内部深度异常及独立范围外候选继续返回无可信事实。剔除数量与阈值进入审计记录。 |
| 搬运预测来源 | 仅在闭爪且双侧接触支持 `holding_object_id=object` 时使用 TCP 位移。未确认接触的目标平移不能借预测放行。预测不读取目标真值位置。 |
| lift 稳定保持 | 成功 LIFT 后保持现有执行器目标，实际推进至少 0.6 秒仿真时间，按 0.1 秒间隔重新采集 RGB-D。抬升高度和稳定性来自视觉目标中心序列，而非 TCP 高度替代值。 |
| hold 接触与取消 | physics observer 在每步调用 `monitor_physics_state`，同时检查运行期限、取消与连续双侧接触。接触丢失在首个坏步停止；取消第 3 步的反例保留 3 步且 `complete=false`，最终清除持续接触检查标志。 |
| 遮挡下的 hold | 缺少视觉目标中心不生成通过的 lifted/stable 事实。完全遮挡或未实际抬升的测试均停止，不把仅有夹爪接触当作视觉稳定成功。 |
| 部分动作记录 | 执行前记录 ACTION_STARTED。技能异常仍根据实际 physics step 增量更新动作分母，并写 PARTIAL_SKILL_RETURN；被动保持中断写实际步数而非请求步数。 |
| 初始急停 | 初始 robot estop/collision 在模型与动作之前路由 hard safety STOP。 |
| 最短截止时间 | 模型等待预算取 episode 剩余时间与 verification 剩余时间的较小值，返回后再次检查有效性。预算耗尽不能被单个 PASS 绕过。 |
| 评分与在线隔离 | observer 收集的物理真值样本仅送末尾独立 evaluator；在线路由使用 RGB-D 与机器人本体状态。物理 evaluator 的结果不能改变已经结束的在线动作选择。 |
| 配置证据 | tracker 阈值与 lift 时间、间隔、高度、稳定性阈值写入 policy.json 的 development_config，可与本次源码指纹对应。 |

## 独立验证

下列命令退出码为 0：

```bash
.venv/bin/python -m pytest -q \
  tests/test_rgbd_closed_loop.py \
  tests/test_rgbd_task_semantics.py \
  tests/test_rgbd_online_verification.py
```

结果：`93 passed in 0.94s`，包括最终闭环 28 项、独立语义 24 项、既有在线条件与预算 41 项；全部为 CPU 测试，没有访问 GPU 或模型服务。

另运行 5 个独立 CPU 反例，全部通过：

1. 初始连续红色支持变为两片，裂隙深度为 0：拒绝身份确认。
2. 同一裂隙深度为原物体表面的 1.0：拒绝将其解释为前景遮挡。
3. 同一裂隙深度为背景的 1.2：拒绝将其解释为前景遮挡。
4. 未确认抓持时目标平移两个像素，超出原历史支持容差：拒绝搬运预测。
5. hold 在第 3 个物理步触发取消：立即抛出 CANCELLED，保留实际 3 步与 `complete=false`，持续接触标志恢复为 false。

复现这些附加反例：

```python
from dataclasses import replace
from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.vision.execution import RGBDTargetTracker, _EpisodeStopped
from tests.test_rgbd_closed_loop import _tracked_scene, _lift_hold_run

evidence = {
    "original_pixel_target": [10, 12],
    "original_pixel_destination": [30, 30],
    "top_grasp_support_height_m": 0.0,
}
for depth in (0.0, 1.0, 1.2):
    tracker = RGBDTargetTracker(_tracked_scene("initial"), evidence)
    assert tracker.facts(_tracked_scene("gap", split_depth=depth), RobotState()) == {}
tracker = RGBDTargetTracker(_tracked_scene("initial"), evidence)
assert tracker.facts(_tracked_scene("unattached", moved_pixels=2), RobotState()) == {}

run = _lift_hold_run()
run.policy = replace(run.policy, cancelled=lambda: run.backend.total_physics_steps >= 3)
try:
    run.hold_lift()
except _EpisodeStopped as exc:
    assert str(exc) == "CANCELLED"
else:
    raise AssertionError("cancel did not stop hold")
assert run.backend.total_physics_steps == 3
assert run.require_continuous_grasp is False
partial = [row for row in run.records if row["layer"] == "PASSIVE_OBSERVATION"][-1]
assert partial["physics_steps"] == 3 and partial["complete"] is False
```

## 源码与测试指纹

以下均为 SHA-256，路径相对仓库根目录。更改这些文件后，当前结论应重新核对。

| 文件 | SHA-256 |
| --- | --- |
| `src/cloud_edge_robot_arm/vision/execution.py` | `5e341862000de281cebfe0981acf781eb23b2cd135e8e51db93e730dbeaddb5a` |
| `src/cloud_edge_robot_arm/vision/evaluation.py` | `10b7d88d65413e454cad00d6f0da8f28be1747017d6baa6e75b1be1504eedbc5` |
| `src/cloud_edge_robot_arm/vision/observations.py` | `1114e6b2de4107ae516f12f8972fcb3b6f71eae7ae5a45bf93adfeb4aa673bb8` |
| `src/cloud_edge_robot_arm/vision/request_control.py` | `773cc153a52c8aeb8a2616a548a89c98d87b86a8d45313f537af8e9713ede07f` |
| `src/cloud_edge_robot_arm/edge/evidence/conditions.py` | `aa08533ed193a71a5a197ba5ca15a1c69523a4059b38c0ca3946886faa968849` |
| `src/cloud_edge_robot_arm/edge/recovery/verification_router.py` | `31bd8bfddfc699459ca6adcd3305f867e9e8b82be5188a55b1cb82ae161063a7` |
| `src/cloud_edge_robot_arm/vision/task_semantics.py` | `209f7682b3a192880218322efbcffdad891b017edbe9ed88d53d5b0c67010b29` |
| `tests/test_rgbd_closed_loop.py` | `10aa14e399ecfdcaa1f54f6b09f811fe90b5ab32309c0cd9bb88291ffecda77f` |
| `tests/test_rgbd_task_semantics.py` | `c5a4dcf3683317dfd9e46377c01ad8879a1d11165eb0e8184576097dd05d86e7` |
| `tests/test_rgbd_online_verification.py` | `6e22532183eec594b0ae36b6e32121b24859ae4d7182ddcb4985289bf67e232b` |

## 结论边界

本审查支持在当前校准资产、直立方块、可区分颜色和固定开发阈值范围内继续冻结 smoke 验收。它不建立通用物体身份、任意自然语言语义或通用遮挡恢复能力，也不替代正在运行的真实 smoke 结果。

工作台语义 helper 的有限指令终判只阻止错误任务被声明为成功，不能阻止评分前已发生的 wrong-object 动作。该限制已记录在 `docs/rgbd_visual_closed_loop.md`。最终验收必须分别保留 online、physical、semantic 和 task_success 结果。
