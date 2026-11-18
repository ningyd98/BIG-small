# 原生移动相机及视觉伺服复核

复核基线为 `318a546dd3a945bddc076cc06bc3528966a4051a` 和本工作树的未提交补丁。发现 2 项 Important。两项均在 CPU 上以真实 fixed-02 已归档像素和生产测量代码复现。真实 fixed-02 及冻结协议 GREEN 的原始换视角记录均与实际相机、物理时钟及标定相符。没有发现 Critical。

## Important 1 · 一般可恢复错误会接受与请求不符且物理已推进的替代帧

`vision/servo.py:229` 把替代帧 ID、请求位置以及相同模拟时刻的校验放在 `if reobserving` 下。该标志在第 260 行仅由精确非平面错误置位。普通标记不可见和三种可恢复区域错误也会启动换机位，但其替代帧直接进入 `update`。相对于上次成功样本的 100 ms 时间差校验，无法验证同一次恢复期间物理暂停。

在 `native/fixed-02/component/servo-frames/step-05` 取 `sample-0104` 作为最近有效参考，捕获 `sample-0105` 后按原件请求 `sample-0105-view-01` 的相机。模拟采集方错误返回原始 `sample-0106`。新帧在另一个机位，物理已经前进 8 步（33.333 ms）。生产代码仍在 `records` 中登记其 ID `rgbd-7c4bcd9da4bd4751917b8986307df324` 并返回控制目标。该复现中的原图、深度、ID、相机姿态及标定均保持原值。

影响限于采集与换相机回调失配时的拒绝能力。目前同步 MuJoCo 实现在发出相机命令后执行配对采集，两个实跑记录所示校验均匹配。验收应包括普通可恢复错误启动的换相机，以及非平面错误出现在第二次尝试时的同一组约束。

## Important 2 · 非平面重观测接受错误的新标定标识

`vision/servo.py:134–139` 仅比较位姿是否变化与标定版本是否变化。它能检出移动后沿用上一个标识，但另一个不匹配当前内外参的标识会通过。MuJoCo 相机已有明确约定，`simulation/mujoco/camera.py:176–177` 将四项内参和十六项外参按小端 float64 编码后取 SHA256 的前 16 个十六进制字符。RGBD 封包自己的 checksum 只绑定其字段和图像字节。

在 `step-06` 取 `sample-0014-view-02` 作最近有效参考。原始 `sample-0015` 触发 `marker_depth_not_planar`。请求原 `sample-0015-view-01` 的准确位置和朝向，仅将返回帧的 `calibration_version` 改为 `1111111111111111`，按协议重算 RGBD 封包 checksum。该帧内外参对应 `d7ed4da1b0052f10`。生产 marker、区域和 servo 仍登记了 `rgbd-1873b5703c0e486a85a802680667610e` 并返回控制目标。测试中的时钟放回每张原帧的采集时刻，TTL 和 2 mm 检测器均按原规则运行。

这说明现有错标定负例只覆盖了旧版本号复用，无法代表所有错标定。当前正常真实和协议回放的所有恢复观测中的版本号均可从原内外参正确复算。

## 控制状态与证据

- `pose_markers.py` 的中心和四角到平面残差阈值均为 0.002 m，坏帧返回 UNKNOWN 且测量没有姿态。精确错误字符串启用深度重观测。默认关闭，调用方需通过显式 MuJoCo 组件、角色和资产校验。RETREAT 还绑定当前任务、步骤、起点、固定垂直端点、张开的空夹爪及非继续段。
- 遇到 marker、区域或端点拒绝时，`_last`、`_accepted_marker`、`_last_target` 与视觉记录不会提交。通过 marker 后的临时候选 `_observed_marker` 可在区域拒绝前写入，提案只读 `_accepted_marker`。显式非平面 RETREAT 替代帧在提交前检查当前区域。有效视觉测量会先写视觉记录，随后才作 SERVO 安全检查、提案计算和控制期限检查。控制接纳应使用 `control_samples` 和检查结果复核，不能仅数 `visual_samples`。组件在盾拒绝时终止，提案刷新位于盾通过之后。
- 相机排序取注册的物体至 marker 偏移、实测 marker 旋转、初始测得的物体与区域几何，以及 hand 和左右指三个注册机器人几何体的 FK。未见在该排序读取后端物体位姿、实例分割或物理成功状态。提案在技能开始清空。非平面恢复时提案的 observation ID、checksum、标定版本及注册 hash 必须与最近成功测量一致。
- 逐样本复核两个运行中所有恢复组。每个运行 759 个视觉样本对应 759 个控制样本，10 次恢复共 12 个相机移动，其中 6 次因非平面拒绝。每次最多 2 个替代视角；原件中相机位置与请求相符，同组采集 sim_time 相同，组内相机命令之间无关节目标。已用提案绑定上一个有效样本。两次 RETREAT 恢复帧均有 4 个当前区域角点。两份原件均有 777 次 SafetyShield 允许记录。
- 冻结协议回放与真实 fixed-02 分别测得最大 sample + IK 为 **86.16 ms** 和 **83.71 ms**。两者 worker SUCCEEDED、组件完成、独立物理成功；8 个源技能产生 9 段，含两段 RETREAT，最终标记两帧均为 OBSERVED。真实 fixed-02 的 seed 为 42001，4 次本地生成、1 次模型加载、1 次云请求。回放为 4 本地/1 云协议响应，0 实际加载、生成和联网。两者顶层 success=false，正式研究 NOT_ACCEPTED，新增合格组 0。
- 回放和 fixed-02 的 result.json SHA256 分别为 `1cb545ee5a68ea29a632a7a630330d6d2f0660a46c3cbbfa16afbf8a6e3ab852` 和 `46427f3aad095225742ced8f45f98f19a2b1951f514f65c9e08ba0cd06c82204`。回放 full-source-sha256.txt 全部 8 项匹配。本次复核只使用已有原件和短 CPU 检查，无 GPU/API、无控制器运行、无源码变更。其余真实试次不计入本报告。

## 两个负例的复现入口

在本工作树根目录，用 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python` 运行下方脚本。相机和物理设备由归档回调替代，marker、严格区域测量、目标计算、视觉记录提交均使用工作树实装。回调记录的时间取自原件；唯一人工损坏的封包字段位于第二个负例。两例均以生产方法返回和末条视觉记录作为复现判据，无物理或关节命令。

```python
import json, base64, hashlib, struct
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker
from cloud_edge_robot_arm.vision.observations import RGBDObservation
p=Path("experiments/results/phase9/real-harness-20261118/native/fixed-02")
def read(f): return json.loads(f.read_bytes())
def load(folder):
    d=read(folder/"observation.json")
    d={k:v for k,v in d.items() if k in RGBDObservation.model_fields}
    for k,f in [('rgb_png_base64','rgb.png'),('depth_float32_base64','depth.f32'),('valid_mask_base64','valid_mask.u8')]:
        d[k]=base64.b64encode((folder/f).read_bytes()).decode()
    return RGBDObservation.model_validate(d)
class Clock(datetime):
    @classmethod
    def now(cls,tz=None): return cls.value
e=read(p/"planning/planning-stage-02.json")["attempts"][0]["draft"]["observation_evidence"]
actions=read(p/"component/episode.json")["actions"]
first=load(p/"component/frames/post-cloud"); Clock.value=first.captured_at
with patch("cloud_edge_robot_arm.vision.tracking.datetime",Clock):
    tr=OpenCVTargetTracker(first,e)
def case(step,ref,bad,good,requested,optin,corrupt=False):
    action=next(a for a in actions if a["step_id"]==step)
    def frame(n): return load(p/"component/servo-frames"/step/n)
    r,b,g,w=map(frame,[ref,bad,good,requested])
    if corrupt:
        g=RGBDObservation.model_validate(g.model_dump()|{"calibration_version":"1111111111111111","checksum_sha256":""})
    def xyz(o): return tuple(o.camera_to_world[i] for i in [3,7,11])
    Clock.value=r.captured_at
    with patch("cloud_edge_robot_arm.vision.servo.datetime",Clock):
        provider=OpenCVServoFeedback(r,tr,e,skill=action["skill"],initial_target=Pose(**action["resolved_step"]["parameters"]["target_pose"]),marker_family_id="side_y_plus_id7_75mm_component_v1")
        def capture(i):
            o=[b,g][i]; Clock.value=o.captured_at; return o
        positions=read(p/"component/episode.json")["camera_adjustments"]
        aim=next(adj["look_at_m"] for adj in positions if "position_m" in adj and tuple(adj["position_m"])==xyz(w))
        view=(xyz(w),tuple(aim))
        result=provider.update_with_camera_views(capture,lambda *args: None,[view],prioritize=lambda *args:[view],allow_marker_depth_reobserve=optin)
        print(step, "accepted",provider.last_observation.observation_id,"reason",provider.records[-1]["camera_recovery"][0]["reason"],"dt",g.sim_time_s-b.sim_time_s,"matches",xyz(w)==xyz(g),"actual calibration",g.calibration_version,"expected",hashlib.sha256(struct.pack("<20d",*g.intrinsics,*g.camera_to_world)).hexdigest()[:16])
case("step-05","sample-0104","sample-0105","sample-0106","sample-0105-view-01",False)
case("step-06","sample-0014-view-02","sample-0015","sample-0015-view-01","sample-0015-view-01",True,True)
```
