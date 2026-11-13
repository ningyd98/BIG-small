# Sol+Molmo 单场景入口

当前入口支持配置准备、标记采集、真实 Sol+Molmo 规划，以及用户授权的 **MuJoCo 组件诊断抓放**。必须显式使用 `--execute --component-diagnostic`；普通 `--execute` 仍因缺少 T10 几何/运动证书而 BLOCKED。组件结果不能充当 T10、G1、B0 或 T8 验收。

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

## MuJoCo 组件诊断执行

沿用上方 NATIVE_PY、CACHE 和参数，将 `--plan-only` 换为下列组合，其他模型、清单、锁、数据库和 site-packages 参数必须全部保留：

```bash
"$NATIVE_PY" -B scripts/run_sol_molmo_single_episode.py \
  --seed 42002 --execute --component-diagnostic --allow-paid \
  --marker-family side_y_plus_id7_75mm_component_v1 \
  --profile-id '<已有Sol配置ID>' \
  --model-control-db /home/ningyd/文档/ChatGPT/BIGsmall/data/model_control.db \
  --model-directory "$CACHE/ordered-small-vlm-20261109/models/Molmo2-ER" \
  --asset-manifest '<既有Molmo资产清单绝对路径>' \
  --gpu-lock "$CACHE/zdtaichu5-9b-fp8-round473/research/.r468-r469-gpu.lock" \
  --application-site-packages /home/ningyd/文档/ChatGPT/BIGsmall/.venv/lib/python3.12/site-packages \
  --output /tmp/bigsmall-single-component-new
```

新变体为75mm标记、沿+Y外伸140mm、零质量零接触，仅用于组件诊断。精确注册SHA和移除37个标记后的XML结构必须与原校准场景一致，不更新原校准SHA或正式释放许可。旧45mm初始检测未知、旧75mm/100mm外伸在放置时遮挡的失败原件保留。

入口创建真实SQLite任务，由 `SimulationWorker.poll_once()` 领取租约并调用 `research.sol_molmo_components.run_component_episode`。桥接用 `vision.molmo_worker.MolmoWorkerPlanner` 主线程运行真实两阶段 PlanningPipeline：一次Sol意图、四次Molmo RGB定位、OpenCV对齐深度和当前支持。补帧在同一暂停模拟时刻完成，不重置租约、预算或采集时间。同步调用仅前后检查截止；原生内部调用并非120秒可强制中断，迟到结果拒绝派发动作。

8核心技能为 MOVE_ABOVE、APPROACH、GRASP、LIFT、MOVE_TO_REGION、PLACE、RELEASE、RETREAT。每步经既有 SkillExecutor 和 SafetyShield；两者消费一致的组件执行视图（现有 resolved_step 参数和10秒技能超时），原始模板与未认证条件另存。控制器返回后进行POST安全检查，然后单独记录观察等待。保留120秒任务预算、16000物理步上限、实际关节位置/速度、TCP工作空间、碰撞、急停及连接检查。

当前RGB-D身份必须可见且唯一；接近阶段需要当前几何/登记标记，搬运阶段可使用当前色块支持与已抓取反馈，但没有完整误差证书。目的地仍须当前可见支持。硬安全每物理步检查；具体租约、开放attempt及截止在动作边界和每50ms墙钟轮询核对，派发前再次核对。失去支持、控制器失败或来源检查失败即停止。离线物体真值仅用于独立物理评价。该分支不经过正式 VisualWorkerRuntime 的T10准入，不填造UNKNOWN证书；普通正式路径保持原样。

结果必须查看 `execution_scope=MUJOCO_COMPONENT_DIAGNOSTIC`、`component_success` 与独立 `physical_success`。即使二者为true，`success=false`、`online_reported_complete=null`、`formal_research=NOT_ACCEPTED`、`qualified_groups_added=0`。软件集成中的云和点位替身与真实模型运行分别记录。

## 输出、退出码和验收

- `scene-assignment.json`：固定场景、标记、预算、资产版本。
- `source-hashes.json`：本入口选择的源码清单；不是整个运行时的完整复现包。
- `before/`、`after/`：如实际采集，包含RGB、float32原始深度、mask、离线实例、元数据和`marker-validation.json`。
- 真实规划另有输入、云后新帧、`cloud-role.json`、模型快照、`planning-response.json`、成本和本地raw。
- 执行模式另有 `planning/planning-stage-01/02.json`、角色与关键源码绑定、`component/episode.json`、逐步控制器/SafetyShield结果、`component/physical-evidence.json`、逐步RGB-D和标记，以及本地runtime/events数据库。末尾采集失败仍保存物理评价并记失败。最终worker终态和来源检查优先于组件文件；超时、取消、发布失败或源码漂移不能保留component_success=true。
- `result.json`：模式、阶段状态、计数、首尾检测、阻塞原因、组件和独立物理状态；未运行的物理/在线完成是null。
- `evidence-manifest.json`：已保存文件的字节和SHA256，包含result但不包含自身。失败时仍保存已有原件。

退出0：PREPARED/MARKER_CHECKED/PLANNED，或组件完整且独立物理成功；退出2：未开始、失败或规划拒绝；退出3：执行受阻。必须结合mode与scope解释，退出0不能单独解释为正式抓放验收。

任务成功必须同时有在线完成和独立物理成功；定位/规划通过不能代替抬升≥50mm并稳定保持≥0.5秒、释放后在目标区稳定≥1秒。单例不形成成功率。进入后续研究仍需当前路径资格、独立静态/安全证据和合格B0；静态≥90%、整体≥80%、安全违规≤1%。之后先四周期selection，再新120组基础先导和INITIAL。

本入口不生成正式冻结包。来源清单和模型身份只能绑定软件/请求配置；组件完整动作不产生正式研究冻结许可。

## 本轮实际结果

2026-11-13新140mm变体真实Sol+Molmo单例：8技能、worker SUCCEEDED、component_success=true、独立physical_success=true；抬升约178mm，保持1.26秒，释放后稳定4.40秒，检查范围内未记录安全违规。20帧标记15次OBSERVED、释放后5次UNKNOWN，连续可见性尚未成立。首次真实版本因遗漏云配置版本号在动作前停止，修复后第二版本成功；失败原件保留。完整边界、验证与派生指标见artifacts/research/process/20261113-sol-molmo-execution/step-report.md及verification-summary.json。这不是G1成功率或T8 120组结果。
