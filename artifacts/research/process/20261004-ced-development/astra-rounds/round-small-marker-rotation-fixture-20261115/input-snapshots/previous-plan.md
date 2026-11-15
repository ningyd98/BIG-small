# SUBPIX 混合标记歧义修复 Implementation Plan

> **For agentic workers:** 后续确获实施授权时，使用 superpowers:executing-plans 按步骤执行。本轮只制定计划，不实施、提交或推送。

**Goal:** 当 SUBPIX 回退同时精确识别出 ID7 和外来 ID0 时，保留歧义并返回 UNKNOWN。

**Architecture:** 回退解码先返回完整的精确解码候选集合，再由已有唯一注册标记门禁判断。保留原亚像素细化、采样、零比特纠错、几何阈值和原生成功检测路径。

**Tech Stack:** Python、OpenCV ArUco、NumPy、Pillow、pydantic、pytest。

**Spec:** 用户本轮 AGENTS.md 直接指令及父任务审查委派；输入字节清单见 `plan.json.inputs`。实际规划模型：**gpt-6-astra**。状态：**PLAN_ONLY_NOT_IMPLEMENTED**。

## 问题、失败证据和根因

源工作树：`/home/ningyd/.codex/worktrees/molmo-absence-protocol-1472/BIGsmall`；HEAD：`5e68e2f9f1ed7d865f483f41534dec9404c83394`。正在审查 Gemini 未提交修改，HEAD 本身不能代表输入版本。

`_decode_subpix_rejected_candidates` 仅将采样矩阵与注册 `marker_id` 比较，忽略外来字典 ID。原生检测无 ID 时，`detect_pose_marker` 用此过滤结果替代完整候选，因此 `(7, 0)` 变成 `(7,)`，绕过 `len(observed) != 1` 的歧义门禁。320×240、14px、5° 的合成画面能稳定复现；ID7 和 ID0 都可在同一候选集合中精确解码。

| 合成输入 | 当前结果 | 必须保持或修复为 |
|---|---|---|
| 单 ID7 | OBSERVED `(7,)` | OBSERVED |
| 单 ID0 | UNKNOWN，ID 被丢弃 | UNKNOWN，保留 ID0 |
| ID7 + ID0 | **OBSERVED `(7,)`** | **UNKNOWN / foreign_or_ambiguous_marker** |
| ID7 + ID7 | UNKNOWN `(7,7)` | UNKNOWN，保留重复数量 |

`sol_molmo_components.py::_ground_component` 在完整目标几何缺失时会消费 OBSERVED 标记生成抓取坐标；这说明错误有实际消费路径，但本轮没有执行该抓取，也没有证明真实机械臂失败。

原始命令（cwd 为源工作树）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python /tmp/bigsmall-gemini-review-20261115/reproduce_marker_ambiguity.py > /tmp/bigsmall-gemini-review-20261115/repro.stdout 2> /tmp/bigsmall-gemini-review-20261115/repro.stderr
```

原始退出码 1，断言为 `Expected ambiguity rejection for recoverable ID7 + ID0; current fallback discards ID0`。`original-evidence/` 保留原始四文件逐字节只读副本；**不要重跑该命令覆盖原目录证据**。本 Astra 另在 `independent-recheck/` 只改输出位置进行独立重跑，仍以同一断言退出 1，四组结果一致。

父任务独立工具执行的 9 文件测试为 335 passed in 10.96s，8 文件 Ruff 为成功。复现 JSON 中这两字段只是父任务结果抄录，复现脚本本身没有执行测试或 Ruff，本子任务也没有重复该测试组。这些通过结果不能否定新增反例。

## 全局约束和运行前置条件

- 本轮仅写本计划目录；不改源、测试、原实验字节，不 commit/push，不运行云、模型、机器人或真实 episode。
- 最小未来修改范围仅 `src/cloud_edge_robot_arm/vision/pose_markers.py` 和 `tests/test_pose_marker_evidence.py`。研究组件仅是只读影响分析依据。
- 不改变控制器、物理、评价器、任何容差、相机或标记方案。保留零比特误差，不能通过增加纠错或忽略候选来通过检查。
- 运行解释器 `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`；工作树 `.venv` 为指向共享环境的符号链接。`runtime-preflight.json` 记录已检查版本和 ArUco 能力。合成复现不需要 GPU、GL 渲染或网络。
- 使用 `PYTHONDONTWRITEBYTECODE=1`；pytest 使用 `-p no:cacheprovider --basetemp=/tmp/<本次唯一目录>`；Ruff 使用 `--no-cache`，其他缓存只落允许目录。
- 源工作树当前在父任务允许写入范围之外。未来实施先取得合法写权限，或在允许位置构建保留所有当前脏修改字节的隔离副本。不得以仅 checkout HEAD 的副本替换当前输入；不得覆盖 Gemini 工作。
- 实施前重新核对 HEAD、每个 `plan.json.inputs` 源文件 SHA256、相关脏修改、运行版本与原始失败；如字节漂移改变根因或范围，先回到 Astra。原样失败属于已知 RED；新增根因或计划外失败需新一轮计划。

## Review Focus

1. 单外来 ID、混合不同 ID：必须保留身份信息并拒绝。
2. 同 ID 多实例：不能用 `set(ids)` 合并后接受。
3. 单目标的四种旋转：ID 和角点顺序必须一一对应，姿态语义保持。
4. 空白、无效码字、损坏边框：不能增加近似匹配，不能强行映射为注册 ID。
5. 原生检测成功和 NONE 模式：维持既有门禁；本轮修的是原生无 ID 时的回退路径，不证明所有未知或不可解码候选均能被识别。

## Task 1：完整回退身份集合和聚焦回归

**Files:** 修改上述唯一两个允许文件。消费 `RGBDObservation`、`PoseMarkerRegistration`；保持 `detect_pose_marker(..., corner_refinement="SUBPIX") -> PoseMarkerEstimate` 公共接口。私有辅助函数可移除 `marker_id` 参数并同步内部调用，使回退不再以目标 ID 过滤；若这样做，原始复现驱动仍冻结为旧版 RED 证据，GREEN 使用新公共接口测试，不能为让旧脚本能运行而修改冻结副本。

- [ ] **Step 1 — 输入复核与 RED 测试。** 从冻结复现提取 320×240、14px、5°、中心 `(100.5,100.5)` 与 `(200.5,100.5)` 的公共接口 fixture，保持深度 1.33、intrinsics `(350,350,159.5,119.5)` 与注册尺寸 0.0525。新增 `test_subpix_rejected_candidates_preserve_foreign_marker_ambiguity`：对 `(7,0)` 和交换左右顺序 `(0,7)` 断言 UNKNOWN、reason `foreign_or_ambiguous_marker`、排序后的 observed IDs 为 `[0,7]`，中心/旋转/yaw 均为 None。基线须先确认原生 ids=None；回退前提不成立视为环境漂移，不能默认为通过。
- [ ] **Step 2 — 保存预期 RED。** 运行下列聚焦命令，记录完整 stdout/stderr、退出码及输入 SHA。应在 OBSERVED 与 UNKNOWN 的断言差异失败，而不是 import 或 fixture 错误。
- [ ] **Step 3 — 最小实现。** 在现有采样后，对 `DICT_4X4_50` 的 50 个含黑边框 6×6 精确码字和四种旋转逐一核对；逐候选输出真实 ID 与对应有序角点，不预筛注册 ID、不按 ID 去重。每候选只输出一个无歧义精确匹配；若发现字典多义匹配则停止并回报，不能任取首项。让已有唯一标记检查拒绝外来或多个标记。无需改 `_ground_component`。
- [ ] **Step 4 — 对照测试。** 新增参数化 `test_subpix_rejected_candidates_identity_controls` 覆盖单 ID7 OBSERVED、单 ID0 UNKNOWN、双 ID7 UNKNOWN；新增四旋转单 ID7（角点姿态与旋转相符，沿用现有容差）；空白和损坏边框/无效完整码字 UNKNOWN；原生较大 48px 混合 ID7+ID0 UNKNOWN。保留并执行已有 NONE 路径、深度、裁切、尺度、相机、边框检查，所有 UNKNOWN 都没有可消费姿态。损坏码字 fixture 先确认它不等于字典任何旋转，避免意外生成另一合法 ID。
- [ ] **Step 5 — GREEN 和回归。** 同一聚焦命令通过，再运行整个 pose marker 测试与父任务 9 文件组合，以及两修改文件 `ruff check --no-cache`。不得更改阈值或删除负例换取绿色。任何计划外失败暂停受影响修复，再由 Astra 规划。
- [ ] **Step 6 — 报告和未来交付。** 保留 RED/GREEN、对照日志、源前后 SHA、diff、运行条件与未覆盖边界，写步骤报告并汇入阶段总结。只有日后得到实施授权且验证通过，才按明确文件路径提交和推送研发分支，并核对 local/upstream/remote SHA；当前审查轮次不执行该步骤。

聚焦命令（未来实施时，cwd=经复核的合法源副本）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider --basetemp=/tmp/bigsmall-subpix-ambiguity-focused-20261115 tests/test_pose_marker_evidence.py -k 'subpix_rejected_candidates' -q
```

完整验证命令模板（本次独立目录替换旧 basetemp，避免覆盖证据）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider --basetemp=/tmp/bigsmall-subpix-ambiguity-green-20261115 tests/test_finger_limit_fix.py tests/test_finger_limit_verification.py tests/test_sol_molmo_component_safety.py tests/test_visible_cuboid_geometry.py tests/test_opencv_target_evidence.py tests/test_pose_marker_evidence.py tests/test_pose_marker_visibility.py tests/test_cloud_vision_fallback.py tests/test_molmo_grounded_planner.py -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff check --no-cache src/cloud_edge_robot_arm/vision/pose_markers.py tests/test_pose_marker_evidence.py
```

## 验收边界

软件通过仅说明明确列出的解码歧义回归被修复；不代表新 Sol/Molmo 真实运行成功率、真实抓取验证或正式研究验收。现有 `geometric_error_bound_m`、`angular_velocity_bound_rad_s` 仍为 None，`stability_status` 仍为 UNKNOWN。此次独立重跑仅合成 CPU 解码，没有修改运行时代码，没有启动真实实验。完整批量 raw、数据库、模型、凭据、SDK 均不进入交付；此计划包不是远端完整复现包。

## 输入和完整性

`plan.json.inputs` 逐项记录绝对路径、SHA256 和只读快照位置；`hash-manifest.json` 覆盖计划、证据和快照（不自哈希）；`SHA256SUMS` 包括该 manifest。所有原始失败副本可与来源逐字节核对。实施者应在变更前后各核对一次，不能修改冻结字节或清理历史失败日志使验证通过。
