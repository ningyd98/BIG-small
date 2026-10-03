# T3 小模型优化与限定验收

2026-10-03，T3 **DONE**：本地 Qwen3-VL 4B 在原定固定场景门槛下通过真实双图传输、严格技能契约、目标/目的实例命中和顶抓几何检查，4/4 请求通过并冻结。另两批独立开发验证合计 **29/32**，`all_cases_pass=false`，三条失败完整保留。该结果允许进入 T7 开发，不代表在线抓放或正式 G1 已验收。

机器可读结果见 [acceptance.json](acceptance.json)，独立复核见 [final-review.md](final-review.md)。本轮只调用本机 `127.0.0.1:11434`，请求禁用代理；新增模型下载为0，没有训练或微调权重，没有真实硬件动作。

## 修复与优化

优化前，两套本地4B候选在像素坐标提示下目标/目的命中均0/4，见 [Qwen3.5 原探测](../../model-probe/summary.md)及 [Qwen3-VL 原探测](../20261003-t3-vl-candidate/acceptance.md)。本轮诊断的请求、响应和对比保留在 [diagnostics/summary.json](diagnostics/summary.json)，这些参考帧诊断不能计为独立评测。

1. 显式使用 `normalized_1000` 坐标协议，回映到原始分辨率，再读取米制深度；不根据数值猜坐标单位。[Qwen3-VL 技术报告 §3.2.4](https://arxiv.org/html/2511.21631v1)说明其0–1000坐标表示。本地对照支持旧协议不适配这一判断，但没有将多项同时优化冒称单因素因果实验。
2. 提示同时包含完整 JSON schema 和明确的技能顺序，解析禁止重复抓取、顺序错误或中途 HOME。[Ollama 官方结构化输出说明](https://docs.ollama.com/capabilities/structured-outputs)也建议在提示中提供 schema。传输双图与实际请求摘要逐次校验。
3. 从原始 RGB-D 估计顶面、局部水平支撑及夹具 TCP 偏移，记录表面点和估计TCP两个不同量。标定仅限当前 MuJoCo 资产、顶抓朝向与5–10 cm高竖直刚性方块；3×3顶面跨度须≤8 mm，估计指尖离支撑面须≥2 mm。资产/profile必须显式配置，普通相机或未配置来源不能自动套用此标定。未向模型或在线几何输入实例掩码、物体真值姿态或离线候选点。
4. 冻结包绑定权重digest、量化、分辨率、坐标系、抓取profile、生成参数、实际提示/schema/两图摘要、继承参数及源码/资产SHA。配置中的 `temperature=0` 覆盖模型默认值，其余继承项如 `presence_penalty=1.5` 在证据中保留。只读复核会拒绝冻结文件或源码漂移。

这是**推理协议和几何适配优化**。所选模型仍是现有 `qwen3-vl-candidate:4b-instruct`，Q4_K_M，权重digest `d18dda6d10491bbe92186dbc7c854623bf99f48eb75829dbe290ef0f97626107`；原 `qwen3.5:4b` 保持安装，本轮归一化对照中仍不可靠，未选为冻结模型。

## 实际结果

| 验证 | 结果 | 含义 |
|---|---|---|
| 固定S01，1冷+3热，320×240 | 4/4全部门槛通过 | 同布局重复性与设备测量，不是4个独立任务 |
| 独立开发批次一 | 12/12正例，3/4明确拒绝，15/16合计 | seeds 41001–41012、42001–42004 |
| 独立开发批次二 | 11/12正例，3/4明确拒绝，14/16合计 | seeds 43001–43012、44001–44004 |
| 合计32个独立场景/RGB | 23/24正例（95.8%）；6/8明确拒绝（75%） | 无遗漏、重复或基础设施错误；不作为正式G1 |
| 固定探针耗时 | 冷3857.666 ms；热P50 1483.330 ms，P95 1516.045 ms | 热样本仅3次；非流式TTFT为NOT_MEASURED |
| GPU | RTX 4070 Ti SUPER；设备显存采样峰值5740 MiB | 模型报告VRAM 4,236,697,927字节；设备采样并非模型独占连续峰值 |
| 软件与证据检查 | 225项测试、定向Ruff、6源码文件mypy通过；冻结VERIFIED | 有1条既有Starlette弃用警告；不宣称全仓检查通过 |

预登记为 [protocol.json](protocol.json) 和 [追加复测协议](replication-protocol.json)。每个独立场景只调用一次，没有重试、剔除失败、事后降低门槛或取最佳批次。第二批没有修改模型、提示、几何或验收规则；评估脚本仅增加等价类型窄化，首批原源码保存在 [evaluator-source.py](scene-validation/evaluator-source.py)，SHA与其来源记录一致。

三条失败：

- 第一批 `negative_absent-04`、第二批 `negative_absent-01`：模型高置信把机械臂部件当作缺失的紫色方块。深度几何门禁实际拒绝，`observed_scene_present=false`、`contract_step_count=0`。这两例仍计为模型拒答失败，不能算模型识别正确；8/8缺失目标最终都未生成动作步骤，也不能据此外推任意误认都能被几何拦截。
- 第二批 `positive-04`：有目标时模型错误拒绝，返回双null、置信度0、空技能，计为正例失败。

实例掩码可见表面均值仅为诊断指标。第一批 `positive-08` 的掩码存在离散碎片，均值距离46.65 mm不能解释为物体中心或抓取误差；人工只核对该例主块和碎片，未宣称32例全量人工图审。实例命中也不能证明机器人最终可抓稳，必须在T7实测。

## 原始证据与复现

- [固定探针原报告](probe/probe-report.json)、[冻结配置](probe/model-frozen.json)、[请求与来源sidecar](probe/model-frozen-evidence.json)、[只读冻结验证](frozen-verification.json)。
- [第一批汇总](scene-validation/summary.json)、[第二批汇总](scene-validation-43001/summary.json)，各目录的 `assignments.json`、`provenance.json` 及 `cases/` 保留逐例RGB-D、离线实例、请求摘要与响应。
- [pytest日志](pytest.log)、[Ruff日志](ruff.log)、[mypy日志](mypy.log)和[独立审查](final-review.md)。

在仓库根目录先复核当前冻结包：

```bash
.venv/bin/python scripts/probe_rgbd_model.py --verify-frozen \
  --output artifacts/research/process/20261003-t3-small-model-optimization/probe
```

重新实测使用新的输出目录；保留本次验收原件：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/probe_rgbd_model.py \
  --config configs/research/model_qwen3vl_4b_normalized.yaml \
  --output artifacts/research/model-probe-reproduction
MUJOCO_GL=egl .venv/bin/python scripts/evaluate_rgbd_model_scenes.py \
  --config configs/research/model_qwen3vl_4b_normalized.yaml \
  --seed-start 41001 --output artifacts/research/model-scenes-reproduction
```

场景评估器会拒绝非空输出目录，有任何未通过案例就返回非零退出码；本次两批退出码均为1，与 `all_cases_pass=false` 一致。软件回归命令：

```bash
MUJOCO_GL=egl .venv/bin/python -m pytest -q \
  tests/test_rgbd_model_probe.py tests/test_rgbd_model_scene_eval.py \
  tests/test_rgbd_normalized_protocol.py tests/test_rgbd_top_grasp.py \
  tests/test_rgbd_grasp_scope.py tests/test_rgbd_messages.py \
  tests/test_rgbd_planning.py tests/test_rgbd_observations.py \
  tests/test_rgbd_runtime.py tests/test_phase4_cloud_planning.py \
  tests/test_phase11_2_model_control_backend.py
```

T7 已 `READY`，须先验证冻结包并显式通过 `ModelConfigSnapshot` / `resolve_visual_planner` 加载配置。当前默认应用入口没有静默切换模型或启用夹具标定；T7仍须把相机、技能、动作后新帧和三值结果验证接到同一episode，显式消费 `resolved_top_grasp_tcp`，保留UNKNOWN、误拒绝和几何拒绝路径。T8/T6b仍为TODO，正式实验、模型训练和真实硬件验收均未开始。
