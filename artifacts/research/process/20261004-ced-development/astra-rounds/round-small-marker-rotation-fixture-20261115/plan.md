# 14px 标记旋转测试窄修订计划

实际规划模型：**gpt-6-astra**。状态：**PLAN_ONLY_NOT_IMPLEMENTED**。本子任务仅形成计划和诊断证据，没有改生产、测试、运行脚本，没有运行硬件、付费模型或真实 episode，没有提交推送。

## 问题与原始证据

父任务在隔离工作树 `/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`、HEAD `57c4dc0d855f5410fcf497edf47b43cfd24ad74b` 按上一轮计划先写负例。原始 pytest 得到 **4 failed, 9 passed, 20 deselected**：三个身份保留失败属于原计划预期 RED；`test_subpix_rejected_candidates_preserve_ordered_pose[0]` 是计划外失败，实际 yaw 与理想 5° 相差 `0.06536547160602678 rad`，超过新测试的 `0.025 rad`。

原命令和退出码见 `plan.json.raw_failure`，逐字节原日志见 `original-evidence/marker-red.log`；其 SHA 与父任务冻结 `marker-red-original.log` 一致。输入路径、SHA256、快照见 `plan.json.inputs`。实施前必须重核，不能只凭 HEAD 判断脏修改内容。

## 独立诊断与根因

`diagnostic/probe.py` 在 `/tmp` 创建并运行，仅调用现有 fixture 和未修改公共接口；stdout 原样保存在 `diagnostic/probe.stdout`，退出码 0。Python 3.12.3、OpenCV 4.14.0、NumPy 2.5.3。四旋转均原生 `ids=None`、有一个 rejected，公共接口均 OBSERVED。k=0/1/2/3 的 yaw 误差分别为 0.06536547、0.01319826、0.02069643、0.01376181 rad，四个 canonical 角点的象限对应全部正确。

根因是测试把已有 48px fixture 的绝对 yaw 精度要求迁移到 14px、5° 的栅格化图像。现实现明确输出未标定单帧估计；零比特身份正确不等于已知角度精度。原计划“角点姿态与旋转相符，沿用现有容差”在此产生了未获证据支持的精度要求。本轮只替换该句对新增 14px 测试的解释，不调整任何生产容差。诊断支持离散角点顺序正确，不建立真实传感器误差模型。

## 限定修改与独立判据

仅修订 `tests/test_pose_marker_evidence.py::test_subpix_rejected_candidates_preserve_ordered_pose` 及其确有必要的测试期望数据。保持 14px、5° fixture、四种旋转和全部身份负例。已有 `test_ordered_known_marker_rotation_distinguishes_cube_quarter_turns`（48px、0.025rad）逐字保持。

使用显式期望表检查 ordered corners 与图像象限的一一对应：

| quarter_turns | canonical 四角依次应位于 |
|---|---|
| 0 | TL、TR、BR、BL |
| 1 | BL、TL、TR、BR |
| 2 | BR、BL、TL、TR |
| 3 | TR、BR、BL、TL |

图像 y 向下；对每角减去四角均值，以 dx/dy 严格正负分类。0 轴值不算通过，四个角点必须有限。期望表独立写明，不调用生产私有解码函数，也不复制它的 `rotation_k`/`np.roll` 决策。已知 fixture 仅旋转 5°，理想角点清楚位于上述四象限；此判据验证角点身份与排列，没有许诺角度误差界。

每个 k 还须确认原生 ids=None、rejected 非空、公共接口 OBSERVED、observed IDs 为 `(7,)`，防止误测原生成功路径。保留未标定状态语义。可直接删除新增 14px 的绝对 yaw 近似断言，不替换为更大 abs 值。离散四角对应已经是本轮需要的旋转语义判据。

临时诊断证明该判据可拒绝循环移位 1、2、3 和逆序 `[0,3,2,1]`；本轮 probe 已逐 k 验证全部拒绝。实施者按最终采用的期望表再核对一次，保留结果即可，不必新增镜像实现的永久测试。

原身份修复仍按 `round-gemini-subpix-marker-ambiguity-review-20261115/plan.md` 执行：保留全部精确字典 ID 与对应角点，不预筛注册 ID、不按 ID 去重，由已有唯一标记门禁拒绝歧义。本轮不扩大生产算法修改范围；采样、角点细化、几何阈值和零比特纠错要求均不变。

## 执行与验证

1. 核对输入 SHA、HEAD、共享运行环境与工作树合法写权限；已有原计划修改之外若出现影响根因的漂移，重新交 Astra。使用 `PYTHONDONTWRITEBYTECODE=1`、pytest `-p no:cacheprovider` 和全新 `/tmp` basetemp；Ruff `--no-cache`。
2. 先只修订旋转测试，再运行原聚焦命令（更换全新 basetemp）。预期恰好保留 **3 个身份 RED**，四个旋转和其他对照通过。保留完整 stdout/stderr、退出码、测试 SHA；不能将此阶段称为整体通过。
3. 保留并单独执行原 48px 测试。最终 oracle 的错误位移与逆序检查在临时诊断进行，保存原始结果。
4. 再继续已批准的身份修复。按原计划运行聚焦组、整个 pose marker 文件、九文件回归组合及两修改文件 Ruff。任何新增根因或计划外失败暂停受影响工作，另请 Astra。
5. 原始 baseline `.patch` 的 diff-context 空行告警按证据格式诊断记录。保持冻结 patch 字节；`git diff --check -- src/cloud_edge_robot_arm/vision/pose_markers.py tests/test_pose_marker_evidence.py` 仅说明实际源码/测试空白检查结果，不声称全部历史证据已通过该检查。此项不授权修理冻结历史。
6. 保存修改前后 SHA、diff、RED/GREEN、命令和退出码，生成步骤报告汇入父阶段总结。后续已验证交付按父任务既有授权与项目要求执行明确路径提交/推送及 SHA 核对；本规划子任务不执行。

## 验收边界

本轮验收是软件回退路径身份与四角顺序，不能替代14px几何精度标定、真实运行或正式研究验收。`geometric_error_bound_m` 与 `angular_velocity_bound_rad_s` 继续为 None，`stability_status` 继续 UNKNOWN。不改原始实验字节、不清理失败日志；计划与派生报告不是完整远端复现包。

规划文件生成时一次未限定 `python` 调用因别名不存在退出 127；改用上述已验证的绝对 `.venv/bin/python` 后成功。原始终端文本和处置记录见 `diagnostic/planning-runtime.log`，没有产生生产/测试变更，也不改变本轮测试根因或范围。
