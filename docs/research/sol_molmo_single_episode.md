# Sol+Molmo 单场景入口

当前入口统一了配置准备、标记采集、真实 Sol+Molmo 规划及证据输出。**完整物理抓放尚未接通：`--execute` 会明确返回 BLOCKED。** 不回退到 LEGACY，不把原始标定资产的资格转给标记资产，不改现有 SafetyShield、OpenCV worker 或动作来源门。

## 环境与默认行为

在当前 BIGsmall 工作树运行。脚本会优先导入自己的 `src`，避免共用虚拟环境导入另一份检出。

```bash
cd /home/ningyd/.codex/worktrees/molmo-absence-protocol-1472/BIGsmall
APP_PY=/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python
export MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1
"$APP_PY" -B scripts/run_sol_molmo_single_episode.py \
  --seed 42001 --output /tmp/bigsmall-single-dry-new
```

默认 dry-run 不加载模型、不读取凭据、不渲染、不推进物理。退出0只说明所选准备检查完成，`result.json` 中仍为 `success=false`、`physical_success=null`。所有输出目录必须全新，既有目录拒绝覆盖。

场景是注册资产中的固定 `S01_NORMAL_STATIC`，320×240顶视相机、1/240秒物理步长、120步稳定；不使用被保留的基础/正式场景池。seed控制配置身份，**更换seed不代表独立随机场景**。指令固定为把红块放到绿色区域。

## 标记采集

```bash
"$APP_PY" -B scripts/run_sol_molmo_single_episode.py \
  --seed 42001 --check-marker --output /tmp/bigsmall-single-marker-new
```

默认 `outboard_id7_45mm_v3` 对应 `scene_pose_marker_outboard_v3.xml`：ID7、DICT_4X4_50、45mm，资产字节按 `marker_families.py` 中的哈希检查。可显式指定已登记族，如 `--marker-family side_y_plus_id7_75mm_r593`；新族依然是 prepare-only。

检测返回 OBSERVED 或 UNKNOWN，具体原因另列；UNKNOWN不自动改称OCCLUDED。首尾两个采样都可见只表示这两个时刻，`continuous_visibility_proven=false`。该模式不抓取，不能证明抓取后的标记可见性。实例ID只作为离线原件保存，不进入检测或几何生成。全无效深度仍保留RGB、原始深度和mask，深度预览明确不可用。

## 真实 Sol+Molmo 规划

使用已经验证的 Molmo 专用运行时，不能用应用环境的不同 Torch/Transformers 替换它。专用环境若缺少应用的 cryptography 等依赖，可把已有应用 site-packages **追加在后面**；不安装或升级依赖。

```bash
CACHE=/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache
NATIVE_PY="$CACHE/ordered-small-vlm-20261109/runtimes/molmoer-r505/bin/python"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
"$NATIVE_PY" -B scripts/run_sol_molmo_single_episode.py \
  --seed 42001 --plan-only --allow-paid \
  --profile-id '<已有Sol配置ID>' \
  --model-control-db /home/ningyd/文档/ChatGPT/BIGsmall/data/model_control.db \
  --model-directory "$CACHE/ordered-small-vlm-20261109/models/Molmo2-ER" \
  --asset-manifest '<既有Molmo资产清单绝对路径>' \
  --gpu-lock "$CACHE/zdtaichu5-9b-fp8-round473/research/.r468-r469-gpu.lock" \
  --application-site-packages /home/ningyd/文档/ChatGPT/BIGsmall/.venv/lib/python3.12/site-packages \
  --output /tmp/bigsmall-single-plan-new
```

API key不作为CLI参数，也不写入场景配置。入口以只读SQLite连接查找明确的profile_id，经 `ModelControlService` 使用该数据库已有的加密secret store；不新建数据库、不激活profile。只接受启用的、精确 `gpt-6.1-sol` 配置。官方路由与参数继续由 `resolve_cloud_role` 校验。

实际组装是 `build_molmo_grounded_planner(service, profile_id, point_provider, task, ...)`，返回 `MolmoGroundedPlannerAdapter`。Molmo BF16只看RGB，OpenCV消费对齐原始深度，Sol只返回技能意图。`RoleModelBundle`并非`cloud/local`二元模型容器，不能传给`resolve_visual_planner`。

单次预算：最多1次权重加载、4次原生定位、1次云请求、0重试/修复。先加载模型，再采集输入，避免把冷加载时间计入帧龄。云端返回后，在**同一暂停物理会话**进行新采集，保持sim_time_s、使用真实的新帧身份与采集时间；不改旧时间、不复用旧帧、不放宽5秒门。随后走原PlanningPipeline、云后复核及最终准入。该模式的PLANNED只表示规划有效，没有执行抓放。

## 执行状态和剩余工作

```bash
"$APP_PY" -B scripts/run_sol_molmo_single_episode.py \
  --seed 42001 --execute --output /tmp/bigsmall-single-execute-new
```

当前输出BLOCKED、退出码3、模型/动作调用均0，至少包含：

- `marked_asset_not_qualified_for_visual_episode`：旧视觉episode要求精确标定资产，标记XML不是该原始资产。
- `molmo_live_opencv_worker_handoff_not_integrated`：Molmo的专用主线程、云后新帧与真实OpenCV worker的合同/来源/动作资格交接尚未实现并验收。不能直接把它交给旧`bounded_model_call`后台线程。
- 对新标记族另报 `prepare_only_marker_family_no_execution_release`。

后续需完成合法的标记资产动作资格和Molmo到真实OpenCV worker的交接，再验证完整抓放。已有 `run_visual_episode`、worker/runtime和SafetyShield继续持有执行权；本入口不提供第二套裸控制器执行器。

## 输出、退出码和验收

- `scene-assignment.json`：固定场景、标记、预算、资产版本。
- `source-hashes.json`：本入口选择的源码清单；不是整个运行时的完整复现包。
- `before/`、`after/`：如实际采集，包含RGB、float32原始深度、mask、离线实例、元数据和`marker-validation.json`。
- 真实规划另有输入、云后新帧、`cloud-role.json`、模型快照、`planning-response.json`、成本和本地raw。
- `result.json`：模式、阶段状态、计数、首尾检测、阻塞原因和真实任务状态；未运行的物理/在线完成是null。
- `evidence-manifest.json`：已保存文件的字节和SHA256，包含result但不包含自身。失败时仍保存已有原件。

退出0：PREPARED/MARKER_CHECKED/PLANNED；退出2：未开始、失败或规划拒绝；退出3：执行受阻。不能把退出0解释为抓放成功。

任务成功必须同时有在线完成和独立物理成功；定位/规划通过不能代替抬升≥50mm并稳定保持≥0.5秒、释放后在目标区稳定≥1秒。单例不形成成功率。进入后续研究仍需当前路径资格、独立静态/安全证据和合格B0；静态≥90%、整体≥80%、安全违规≤1%。之后先四周期selection，再新120组基础先导和INITIAL。

本入口不生成正式冻结包。来源清单和模型身份只能绑定软件/请求配置；实际完整动作与研究资格未成立时不制造冻结许可。
