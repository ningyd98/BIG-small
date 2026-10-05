# 步骤49：原相机与控制器下的可见标记实测

日期：2026-10-05。一次排除于正式池的实际 MuJoCo 开发搬运，初始与全部九个动作后帧均识别到 ID7：**10/10 OBSERVED**。原中心标记的同一物理场景仍保留初始可见、九个动作后 UNKNOWN 的失败。本步解决这个开发场景的动作后可见性，不发布几何、连续运动或正式实验验收。

## 新资产与不变的物理路径

新增 `vision/pose_marker_visibility.py`、`tests/test_pose_marker_visibility.py` 和独立资产 `scene_pose_marker_outboard_v3.xml`。资产 SHA 为 `ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23`。既有45mm ID7及完整 quiet 区沿物体局部 X 移出100mm，仍刚性绑定于同一物体；仅37个无质量/无接触视觉几何移动。70mm红色方块的实际碰撞范围、质量、关节、执行器、相机和控制器不变。

此为模拟视觉附件，没有宣称实体安装、重量或碰撞验收。基础资产、中心标记v1/v2和默认配置未改写，新版本不用于在线动作准入。编译后原物理/相机/控制器参数一致；相较未标记基础资产，`model.stat.meansize` 因视觉几何改变，不能宣称所有渲染统计相同。

同一640×480顶视相机、位置 `(0.35,0,1.4)`、原朝向/fovy50、原教师和唯一 `MuJoCoMotionController` 完成一次 NORMAL 搬运。新 scene/group 绑定新资产，见 [header.json](header.json) 与 [排除记录](development-exclusion.json)。没有更换控制器、调目标或重试；attempt目录已存在时脚本拒绝再次执行。

## 实际运行与独立结果

- 实际9个已记录动作、743条控制命令、4806物理步和4807个物理状态样本；模型调用为0。
- 独立评分 SUCCESS，抬升约103.9mm，稳定双侧保持约0.7625秒，放置稳定约2.1542秒；安全仅按既有检查范围登记 `SCOPED_NO_VIOLATION`。
- 初始与 MOVE_ABOVE、APPROACH、GRASP、LIFT、保持、搬运、PLACE、RELEASE、释放后保持全部 OBSERVED，最短边16–18像素。完整结果在 [observability.json](attempt-1/observability.json)。
- 1次setup RGBD采集和10次显式边界 RGBD/instance 采集；仍使用原开发脚本的缓存像素更新抑制，记录765次被抑制更新。此为脚本内采集节奏，不宣称与原缓存渲染节奏等价。教师 `robot.observe` 或缓存sensor读取会明确失败，实际控制和物理采样保持原路径。
- 保存所有物理、执行器、动作、命令、帧和原始字节hash。decoder 仅接收真实 RGBD 与已知 ID/尺寸/资产，不读物理真值；独立评分和误差诊断在离线进行。

[离线核验](offline-verification.json)从保存资料重算原始hash、episode/step/command/action关联、独立评分及10次严格decoder重放。独立复审另外逐字段比较4807个完整物理状态：除新的episode_id外，与原中心标记那次运行完全一致，支持此次视觉改变没有改变这条已记录的物理路径。见 [独立审查](independent-review.md)。

真实帧离线误差最大值为：marker中心约0.941mm、按固定附件变换推回物体中心约6.393mm、旋转约0.063192rad。后两者反映小标记姿态误差会由100mm附件偏置放大，不能直接复制到 native bounds。10帧投影标签区域的离线5mm前景诊断均为0；这是原始深度诊断，未作遮挡误差校准。

## 代码验证与复现

5个新增测试先因缺失实现产生合格 RED。首次GREEN为23通过/1失败：测试误把quiet底面Z写成tag面Z；检查原资产后改为保持原quiet的35.02mm，未改变生成代码。最终 **24 passed / 0.70秒**，独立新增5项 **passed / 0.33秒**；新source/test Ruff与source mypy通过。

实际运行脚本已按执行时字节冻结，另一次脚本Ruff发现其继承的 I001及3处E501；原结果保留在 `script-ruff.log`，没有事后修改实际执行来源。离线verifier的4处静态问题已修复，`verifier-ruff.log`及 `offline-verification-final.log`通过。这是明确范围验证，未运行或宣称全仓通过。

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_pose_marker_visibility.py tests/test_pose_marker_evidence.py
MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. timeout 180s .venv/bin/python artifacts/research/process/20261004-ced-development/t7b-visible-marker-next/run_once.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python artifacts/research/process/20261004-ced-development/t7b-visible-marker-next/verify_offline.py
```

当前目录不能重跑第二条命令；新实测须先新建分配与输出目录。`source/`仅冻结本次28个必要来源，不复制全仓；[source-hashes.json](source-hashes.json)、[source-freeze.json](source-freeze.json)及 `attempt-1/raw-hashes.json`绑定源码与原始证据。原中心标记资料与失败不改名、不覆盖。

一个场景的离散可见帧不能证明连续角速度、完整物体关联、跨组误差覆盖或动作窗口内运动界。native仍缺经独立接受的基本标定来源；风险校准、真实Max、完整机会/200故障、INITIAL/METHOD/FINAL和实际硬件仍未验收。`formal_accepted=false`，边缘型号后置。
