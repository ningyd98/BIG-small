# BIGsmall 交接：V3 真实付费 40 项测试结果与下一步工作（给 Codex）

> 生成时间：2026-11-15。本文只记录已在文件或命令输出中核验过的事实；推断与假设已单独标注。

## 0. 接手须知

- **工作树**：`/home/ningyd/.codex/worktrees/molmo-absence-protocol-1472/BIGsmall`
- **分支**：`codex/molmo-flat-interior-20261111`
- **基线 commit**：`5e68e2f9f1ed7d865f483f41534dec9404c83394`（此前已推送 `ningyd98/BIG-small`，本地、上游、远端三方一致）
- **当前状态**：工作树里有本轮已验证但**尚未提交、尚未推送**的修改（见第 3 节）。
- **规则**：开工前先读仓库 `AGENTS.md`，主要约束如下：
  - 每轮遇到新问题或计划外失败时，先调用 `gpt-6-astra` 生成计划，保存到 `artifacts/research/process/20261004-ced-development/astra-rounds/<round>/plan.md` 和 `plan.json`，然后再实施。
  - **本轮没有调用 Astra，也没有生成 Astra 计划**，需要在阶段总结里如实记录；不得把其他模型的输出标成 Astra 计划。
  - 不得修改冻结原件，不得补造深度，不得为了提高成功率放宽评价标准。
  - 提交要按明确路径进行；推送公开仓库要用户另行授权，推送后核对本地、上游、远端三方 SHA。
  - 新的付费批量测试也要用户另行授权。
- **必须保留的方案**：
  - 顶视相机 `320x240`
  - ArUco 标记 `side_y_plus_id7_75mm_component_v1`
  - `MuJoCoMotionController` / `MuJoCoSkillRobot`
  - 物理模型
  - 39 mm 开指目标
  - `check_component_hard_state` 中手指 0.1 mm 容差
  - `CompletionCriteria('object', 'target_region')`
- **冻结目录（只读）**：
  - `sol-molmo-observability-40-20261114-v1`
  - `geometry-repair-40-20261114-v2`
  - `joint-limit-diagnosis-20261114-v2`
  - `geometry-repair/host-occlusion-controls`
  - `finger-limit-fix-20261114`

  以上目录位于 `/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/`，基线清单见 `next-round-repair-20261114/frozen-dirs-baseline.json`，共 11,388 个文件。

## 1. 本轮代码修复（未提交）

| 文件 | 修改 |
|---|---|
| `src/cloud_edge_robot_arm/vision/tracking.py`（约 L278–299） | P1：在 `OpenCVTargetTracker._geometry` 中，当 `depth_error_bound_m is None` 时吸收 `shaded_edge`。判据为 `norm(chroma-color)<0.24` 或 `norm(pure_chroma-pure_color)<0.20`（漫反射色度，不受高光影响），并同时要求 `ptp>=14`、`valid>0`、深度有限且 `depth>=top_depth_min` |
| `src/cloud_edge_robot_arm/vision/pose_markers.py` | P2：当 `ids is None`、`corner_refinement=="SUBPIX"` 且存在 `rejected` 候选时，调用 `_decode_subpix_rejected_candidates` 解码 |
| `src/cloud_edge_robot_arm/research/sol_molmo_components.py` | P2：`_visible_support` 新增 `reference_mask` 参数；`_ground_component` 传入 `tracker.destination["mask"]`，把分割后的绿色支承区域合并起来计算 |
| `scripts/verify_finger_limit_fix.py` | 增加修复白名单 `ALLOWED_REPAIR_PATHS` / `ALLOWED_GUARD_HELPER_FUNCTIONS`、AST 校验 `_verify_guard_ast` 和 `original_source_bytes` |
| `scripts/verify_next_round_repairs.py` | 新增离线分类、反事实和仿真审计脚本 |
| `tests/test_visible_cuboid_geometry.py`、`tests/test_pose_marker_evidence.py`、`tests/test_sol_molmo_component_safety.py` | 新增对应单测 |

## 2. 离线与软件验证（V3 开跑前完成，均在最后一次编辑 `tracking.py` 之后运行）

| 检查 | 结果 |
|---|---|
| `ruff check`，8 个改动文件 | exit 0，`All checks passed!` |
| 9 个相关测试文件的 pytest（`test_finger_limit_fix`、`test_finger_limit_verification`、`test_sol_molmo_component_safety`、`test_visible_cuboid_geometry`、`test_opencv_target_evidence`、`test_pose_marker_evidence`、`test_pose_marker_visibility`、`test_cloud_vision_fallback`、`test_molmo_grounded_planner`） | exit 0，`335 passed` |
| 遮挡对照重查 `finger-limit-fix-20261114/verification-logs/recheck-controls.py` | 9/9 符合预期：6 个实际遮挡负例被拒绝；2 个正常例通过；缺深度的 `held-out-044008` 被拒绝（`target_depth_incomplete`）；原始 RGB 哈希不变 |
| `scripts/verify_finger_limit_fix.py` | exit 0。40 例（28 例回放、12 例原件核验）全部通过；485 个历史违规步全部捕获；原有 20 个成功例全部保留；手指限位停止步：043003→1189，044009→1198，044011→1777 |
| `scripts/verify_next_round_repairs.py` | exit 0：`frozen_dirs_unchanged: true`、`p1_audit_passed: true`、`p2_all_5_simulated_success: true`、`p1_shaded_simulated_successes: 2`。P3 反事实：`development-043003` 可恢复；`held-out-044009`（第 1214 步）和 `held-out-044011`（第 1449 步）仍然触发 `HARD_FINGER_LIMIT` |
| 全仓库 pytest | **本轮没有运行**。已知存在与本轮无关的失败 `test_model_control_public_api_has_chinese_docstrings`，**不能宣称全项目测试通过** |

## 3. V3 真实付费 40 项测试（用户 2026-11-15 授权）

- **输出目录**：`/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3/`
  - `batch-result.json`、`verification.json`（`integrity_status: "PASS"`）、`actual-40-report.md`
- **控制、冻结与核验文件**：位于 `outputs/next-round-repair-20261114/`
  - `run_40_next_round_repair.py`、`verify_next_round_batch.py`
  - `next-40-authorization.json`
  - `next-40-source-manifest.json`（冻结 594 个文件，源码零漂移，`source_snapshot_variants: 1`）
  - `frozen-dirs-baseline.json`
- **运行情况**：40/40 跑完，exit 0，耗时 1180.48 s，`process_timeouts: 0`，没有重试，`hardware_dispatch: false`，没有 `git push`。
- **用量**：
  - 本地 `Molmo2-ER`：加载 40 次，生成 142/142 次
  - 云端 `gpt-6.1-sol`：请求 40 次，其中文本 31 次、图像回退 9 次
  - tokens：25,896 prompt + 2,868 completion，共 28,764
  - 执行动作 222 个；证据文件 7,041 个，共 925,412,800 字节
- **安全与标记**：`safety_violations: 3`（即 3 例 `HARD_FINGER_LIMIT` 在线停止）；`marker_endpoints_observed: 38`。
- **验收边界**：
  - `formal_research: "NOT_ACCEPTED"`
  - `native_action_qualification: "UNKNOWN_NOT_GRANTED"`
  - `continuous_marker_visibility_proven: false`
  - `qualification_limit`：这是一次已披露的配对组件回归，不代表未见场景泛化，也不构成正式或硬件验收

### 3.1 汇总

| 分组 | V1 | V2 | V3 |
|---|---|---|---|
| fixed | 10/10 | 10/10 | **10/10** |
| development | 0/15 | 4/15 | **9/15** |
| held-out | 1/15 | 6/15 | **8/15** |
| **合计** | 11/40（27.5%） | 20/40（50.0%） | **27/40（67.5%）** |

- **配对迁移**：
  - 相对 V1：`SUCCESS->SUCCESS` 11，`FAIL->SUCCESS` 16，`FAIL->FAIL` 13
  - 相对 V2：`SUCCESS->SUCCESS` 20，`FAIL->SUCCESS` 7，`FAIL->FAIL` 13，**没有回归**
- **27/40 的 95% Wilson 置信区间**约为 52%–80%（自行计算，仅供参考）。

### 3.2 相对 V2 新增的 7 个成功例

| 用例 | 对应修复 |
|---|---|
| development-043001 | P1 shaded edge |
| development-043007 | P1 shaded edge |
| development-043006 | P2 SUBPIX marker |
| development-043010 | P2 SUBPIX marker |
| development-043014 | P2 SUBPIX marker |
| held-out-044002 | P2 SUBPIX marker |
| held-out-044013 | P2 split green support（`reference_mask`） |

### 3.3 40 例逐项结果（摘自 `verification.json`）

所有用例均为 `cloud_requests=1`、`first_stage_reason=WORKER_OWNED_POST_CLOUD_CAPTURE_REQUIRED`。27 个成功例的 `safety_assessment` 全部为 `SCOPED_NO_VIOLATION`。

| 用例 | 成功 | 动作数 | 图像回退 | 标记 前/后 | 最终原因 / 末阶段原因 |
|---|---|---|---|---|---|
| fixed-042001 ~ 042010（10 例） | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| development-043001 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| development-043002 | ✅ | 8 | 否 | OBSERVED/**UNKNOWN** | — |
| development-043003 | ❌ | 2 | 否 | OBSERVED/OBSERVED | `HARD_FINGER_LIMIT` |
| development-043004 | ❌ | 0 | 是 | OBSERVED/OBSERVED | `RGBDModelCallFailed`：`target_depth_incomplete` |
| development-043005 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| development-043006 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| development-043007 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| development-043008 | ❌ | 0 | 否 | OBSERVED/OBSERVED | `CONTROLLER_FAILURE:UNREACHABLE` |
| development-043009 | ❌ | 0 | 是 | OBSERVED/OBSERVED | `RGBDModelCallFailed`：`boundary_depth_in_front_of_observed_top` |
| development-043010 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| development-043011 | ❌ | 0 | 是 | OBSERVED/OBSERVED | `RGBDModelCallFailed`：`boundary_depth_in_front_of_observed_top` |
| development-043012 | ❌ | 0 | 是 | OBSERVED/OBSERVED | `RGBDModelCallFailed`：`boundary_depth_in_front_of_observed_top` |
| development-043013 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| development-043014 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| development-043015 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| held-out-044001 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| held-out-044002 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| held-out-044003 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| held-out-044004 | ❌ | 0 | 是 | OBSERVED/OBSERVED | `RGBDModelCallFailed`：`target_depth_incomplete` |
| held-out-044005 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| held-out-044006 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| held-out-044007 | ❌ | 0 | 是 | OBSERVED/OBSERVED | `RGBDModelCallFailed`：`boundary_depth_in_front_of_observed_top` |
| held-out-044008 | ❌ | 0 | 是 | OBSERVED/OBSERVED | `RGBDModelCallFailed`：`target_depth_incomplete` |
| held-out-044009 | ❌ | 2 | 否 | OBSERVED/OBSERVED | `HARD_FINGER_LIMIT` |
| held-out-044010 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| held-out-044011 | ❌ | 2 | 否 | OBSERVED/OBSERVED | `HARD_FINGER_LIMIT` |
| held-out-044012 | ❌ | 0 | 是 | **UNKNOWN/UNKNOWN** | `RGBDModelCallFailed`：`target_depth_incomplete` |
| held-out-044013 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |
| held-out-044014 | ❌ | 0 | 是 | OBSERVED/OBSERVED | `RGBDModelCallFailed`：`boundary_depth_in_front_of_observed_top` |
| held-out-044015 | ✅ | 8 | 否 | OBSERVED/OBSERVED | — |

### 3.4 剩余 13 项失败

| 组 | 数量 | 用例 | 已知事实 |
|---|---|---|---|
| A. `boundary_depth_in_front_of_observed_top` | 5 | 043009、043011、043012、044007、044014 | 动作前就被拒绝。9 次图像回退都返回了 `CANDIDATE`，但都没过本地深度门。实测报告认为与 4x MSAA 运行时边缘深度尖峰有关，**这一归因还要用逐像素证据确认** |
| B. `HARD_FINGER_LIMIT` | 3 | 043003、044009、044011 | 都在第 2 个动作时被在线监测安全停止（V2 时 044011 曾继续执行，最后以 `GRASP_LOST` 失败）。反事实实验里只有 043003 能恢复 |
| C. `target_depth_incomplete` | 4 | 043004、044004、044008、044012 | 动作前就被拒绝。044008 在遮挡对照里本来就是应当被拒绝的缺深度样本；044012 的标记前后都是 UNKNOWN |
| D. `CONTROLLER_FAILURE:UNREACHABLE` | 1 | 043008 | 视觉和规划都通过（文本请求），执行 0 个动作，IK 不可达 |

## 4. 下一步工作

### 阶段 0：流程补齐（不付费，先做）

1. **提交**：把第 1 节的文件按明确路径提交到本地研发分支，并记录 commit SHA。**推送需要用户另行授权**，推送后核对三方 SHA。
2. **Astra 计划**：针对第 4 节阶段 1 的第一项，调用 `gpt-6-astra` 生成本轮计划，写入 `astra-rounds/<round>/plan.md` 和 `plan.json`。计划内容包括：问题、原始失败证据、输入文件及 SHA256、根因或假设、修改范围、验证方法、运行前置条件、验收边界。Astra 不可用时，明确记录“计划未生成”。
3. **修复已知失败测试**：补全中文文档字符串，修复 `test_model_control_public_api_has_chinese_docstrings`，然后运行全仓库 pytest，并如实报告结果。
4. **获取独立复核**：本轮修改还没有经过第二次独立审查，建议让 Astra 或其他审查者复核第 1 节的 diff。

### 阶段 1：按失败组修复（离线、不付费）

**A 组：边缘深度（5 例，优先级最高）**

- 先用只读方式取出这 5 例冻结的 RGB-D 原件，画出目标掩码边界环的深度分布，确认被拒绝的像素是否只出现在 1–2 px 宽的边缘混合带。
- 首选修复：在深度判据里剔除边缘飞点，比如腐蚀掩码边界，或在边界环上用分位数、中值统计代替最值。这种做法对真实深度相机同样适用。
- 关闭 MSAA（`offsamples=0`）只作为对照实验，不作为主修复。它改变了相机观测，可能触及用户选定的相机方案，需要用户确认。
- **验收**：
  - 6 个实际遮挡负例仍然全部被拒绝；`held-out-044008` 仍然因缺深度被拒绝
  - 原有 27 个成功例离线不出现回归
  - 冻结目录哈希不变

**B 组：手指限位（3 例）**

- 先做只读的根因分析：画出 APPROACH 阶段的手指指令、实际位置、关节上下限和接触力随时间的曲线，区分三种可能：指令贴近上限、执行器过冲、接触挤压。
- 可能的修复点在控制器的手指指令轨迹上，比如限速或渐变，但这会触及用户选定的控制器、39 mm 开指目标或物理模型，**改动前必须先得到用户批准**。
- 不得放宽 0.1 mm 容差。

**C 组：深度不全（4 例）**

- 逐例判断原因：目标靠近视野或桌面边缘、被机械臂或其他物体遮挡、还是深度本来就缺。
- 深度确实不足时，**保留拒绝**，记为安全失败。
- 只有被机械臂遮挡的情况，才可以考虑让机械臂退开后重新拍摄。

**D 组：不可达（1 例）**

- 核对 043008 的目标位姿是否在工作空间内。
- 如果在空间内，尝试多个 IK 初值或换一个抓取偏航角；如果确实不可达，保留为正确拒绝。

**降低成本（可选）**

- 当本地深度门已经确定会拒绝时，跳过付费的云端图像回退：本轮 9 次图像回退全部没有转化为成功。
- 这项改动会影响云端调用路径，需要单独评估并在计划中写明。

### 阶段 2：真实验证（每一项都要用户另行付费授权）

1. **配对回归**：用同样的 40 个 seed 测试阶段 1 修复后的代码，比较 V3 与 V4，要求没有回归。
2. **未见泛化**：held-out 的失败例已经参与过修复诊断（如 044002、044013），所以 held-out 的 8/15 **不能再作为未见泛化证据**。需要冻结代码后，在一批从未分析过的新 seed（例如 45001–45015）上测试一次，并报告置信区间。

### 记录要求

每一轮都要保留原始失败、实施结果和验证证据，生成步骤报告并汇入阶段总结。开发验证、真实运行、正式研究验收三者分开记录，不能用软件测试通过代替真实证据。
