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

## 可选的组件位姿变化

默认仍是固定S01。只有显式组件执行可加 `--scene-split development` 或 `--scene-split held-out`，两者使用独立的诊断采样命名空间，不使用正式基础/留出场景池。记录中的 `component_scene` 指定实际物体位置和绕Z轴的偏航；后端在reset时应用，`component/scene-application.json` 保存初始化后的实际位置与四元数作离线核对。当前仍是同一注册资产的位姿覆盖，不代表多任务或正式场景资格。

每四个种子中一个为 `ARM_OCCLUSION_STRESS`，表示朝机械臂投影区域布置的压力条件，不宣称遮挡已被独立测量。其余为可见位姿条件。未知/不完整轮廓、模型ABSENT和空云规划继续停止；变化条件不保证已有抓放轮廓门一定准入。声明条件以规范JSON标量写入任务参数，并与冻结角色策略逐字比对，不能只改seed或元数据冒充实际变化。

选定组件标记族的RETREAT在原控制器目标上沿世界-Y多退让100mm，实际参数仍由同一SafetyShield与SkillExecutor消费，以避免原终点姿态阻挡标记。检测器、标记资产、相机和资格字段不变。首尾检测成功仍不证明运动全程可见。

只有显式组件诊断的云请求带 `execution_scope=MUJOCO_COMPONENT_DIAGNOSTIC`、`hardware_dispatch=false` 和仿真范围说明；原开发几何未获物理许可的标签与不确定时空规划规则保留。物体初始真值仅写离线审计，不进入Molmo或云端请求。

## 可选云端视觉回退

显式组件执行可追加 `--cloud-vision-fallback`。默认关闭；必须同时使用
`--execute --component-diagnostic --allow-paid`。开关会写入场景分配、任务参数和冻结
角色策略；不一致或运行中变更即停止。普通正式路径不启用该路线。

本地定位和几何成功时，Sol仍只收到原有文字和数值；可恢复的本地识别/几何失败时，
原来的一次云请求改发原始RGB和可选的有边界RGB裁剪，附完整图像尺寸、裁剪映射及
失败原因。云端只返回完整原图上的两个归一化二维候选点及8个受限技能意图，或返回
REOBSERVE/ABSENT。该路线会上传仿真图像并产生图像输入费用，但每项云请求上限仍为1，
不增加重试、物理步数或动作许可。原始深度和离线实例/物体真值不进入云请求。

云端候选不是原生Molmo输出或米制几何。worker必须在云返回后实际采集新帧，按原协议
核对同一暂停会话、RGB字节、标定及深度变化，再运行未放宽的局部关联、原始深度落地
和完整轮廓检查。候选无法解决的轮廓、缺失深度和真实遮挡继续停止。原生绑定、帧龄或
配置、线程、生成预算及未知执行/I/O错误不会触发图像上传。原始输出与解析结果必须一致；
provider主动拒绝的token上限结果还须具备匹配的上限和原始文本哈希证据。
`cloud_vision_fallback`证据保存原失败、图像哈希及裁剪映射；
`grounding_point_source=CLOUD_VISION_CANDIDATE`明确标识云端候选，实际请求/回复仍保存于
`raw/cloud/request.json`和`raw/cloud/response.json`。

新增软件集成验证使用真实MuJoCo/SQLite/worker和明确的模型替身；它证明线路与拒绝
条件，并不证明真实云端识别精度或变姿态成功率。已有40项原件和结论保持不变。

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


### 2026-11-14 observability follow-up results

The matrix was frozen before requests: 10 fixed controls (42001–42010), 15 development
poses (43001–43015), and 15 held-out poses (44001–44015), with fresh sequential native
processes and all failures retained. All 30 varied poses were verified against the
actual initial physics position/quaternion; coverage is one registered asset.

| Group | Physical/component success | Endpoint marker observed |
| --- | --- | --- |
| Fixed controls | 10/10 | 10/10 |
| Development poses | 0/15 | 12/15 |
| Held-out poses | 1/15 | 14/15 |

Marker counts include unchanged endpoints of rejected episodes and are not task success.
All 11 completed physical episodes ended with strictly decoded ID7. The 29 other
episodes stopped before actions and cloud requests: 21 incomplete/occluded contours,
7 unresolved exterior boundary depth, and 1 invalid original depth. The named
arm-occlusion conditions remain intended stress labels, not measured occlusion truth.

The run used 40 model loads, 102 completed local generations, 11 cloud requests and
11 reservations, and 88 actions in 959.2 seconds. SHA256 verification covered 4,417
evidence files (407,178,335 bytes), one identical executed source snapshot, and no
process timeout or source drift. These results improve the fixed diagnostic pipeline;
varied-pose robustness remains poor. Formal acceptance stays NOT_ACCEPTED, native
action qualification UNKNOWN_NOT_GRANTED, qualified groups added 0, hardware dispatch
false. Complete raw data and runtime databases remain local and are not part of the
remote source delivery.

### 2026-11-14 云端视觉接口实测

用户另行明确授权最多3次付费图片请求后，使用已有`gpt-6.1-sol`配置和官方
`/v1/chat/completions`路由，对development-043001、development-043005及held-out-044008
的历史仿真原始RGB和局部裁剪进行离线复核。恰好3次请求、0重试、0动作；均返回通过
严格schema的二维候选，三个目标/目的地点均通过RGB红/绿色度核对。请求中的原图字节
及裁剪哈希与历史原件一致；不上传原始深度或离线实例真值。

耗时4.06–4.09秒/次，用量2,514输入+307输出=2,821 tokens；实际金额未由provider返回。
这证明所选接口可接收图片并按协议返回候选。上述三个原失败分别涉及轮廓、边界深度和
原始深度缺失，候选点本身不能证明几何检查通过。未进行当前帧准入或动作执行，也未
重跑40项；这些精选历史样本不构成识别精度或任务成功率估计。


### 2026-11-14 可见几何修复与下一轮准备

修复用实测 RGB 内部深度锚定顶面，再分类边界，检查整个内部和候选顶面的高度跨度；
不再在分离未决时退回整片掩膜。无深度误差界时沿用既有 8mm 平整度准入，只允许
临时可见支持，完整尺寸与效果资格仍为 UNKNOWN。边界前景、无效原始深度及未决外圈
仍拒绝；所有原深度保留，不补造测量。

固定 0.95 凸度门被半像素足迹下的旋转矩形内部支持检查替换；要求内部已有观测颜色，
不填补缺口，保留孔洞、边界深度、身份、帧龄和后续尺寸检查。无效深度新增内部/边界/
邻接无效背景诊断，物理遮挡物身份仍 UNKNOWN。入口源码绑定包括 tracking.py 和
直接依赖 top_grasp.py。模型、相机、标记、控制器与调用上限不变。

最终相关回归 385 passed（62.52s），修改文件 Ruff 通过。目标模块两条 mypy 诊断及
有界全项目检查遇到的既有中文 docstring 审计失败，均在精确基线 bab220435ab3211adc40b2916325edc28477a00f
独立重现，没有新增诊断；不宣称全项目全绿。一轮全变更 Astra 审查发现的等间隔多层
深度误接受已先复现，修复后同时通过多层负例和正常可见侧面正例。该作者修复经过
最终回归，没有进行第二轮审查或声称 Astra 最终批准。

原始 40 帧只读回放重现 40/40 原门结果，修复后可见几何支持 11→28：固定10/10、
development8/15、原held-out10/15。剩余12项为外圈深度未决3、tracker深度不完整3、
边界前景5、关联原深度无效1。没有新模型请求或动作，原始字节与时间戳不变；该数字
不是任务成功率，旧held-out已是披露的回归数据。所有历史输入均缺深度误差界，完整
尺寸仍 UNKNOWN。宿主原分辨率真实渲染的6组前景遮挡均拒绝，2组正常对照通过可见
支持，桌边无效深度对照拒绝；最终代码又复核了同一批原始帧。

源码 afc43e805ad898d3fce03e2472ca2c174f9fcd9b 交付后，用户又明确授权新一轮最多40次
付费请求。现已完成配对40项实际Sol+Molmo组件回归，显式开启云端视觉回退，0重试、
0超时、0源码漂移。固定10/10、development4/15、原held-out6/15，组件物理成功合计
20/40（50%），原为11/40（27.5%）；原11项成功全部保留，新增9项。变姿态1/30→10/30。
两轮40项初始物体姿态及RGB、原始深度、mask字节均一致，实际帧身份/时间戳为新采集。
这仍是已披露样本的配对组件回归，不是未见泛化或正式验收。

剩余20项按互斥终止原因：12项动作前深度门拒绝（外圈3、深度不完整4、前景边界5）；
5项动作后颜色身份支持不唯一（4项目标红色分裂、1项目的地绿色分裂）；2项硬关节限位
物理安全失败；1项LIFT抓取丢失。抓取丢失样本也有硬限位证据，因此记录硬限位的总数
为3/40，均发生在APPROACH期间。原件只标出越界采样步，不足以确定具体关节/幅度或
限位与随后失抓的因果关系。这些运动阶段问题仍未修复；本轮保持原控制器与拒绝规则。

40次云请求中28次文字/几何、12次图片回退；12次均返回合法候选，但0项通过后续本地
深度门。新增9项成功均走本地几何路线。40次权重加载、136次原生定位、195个仿真技能
动作，总用时1168.48秒；输入26496、输出3383，共29879 tokens，provider未返回金额。
每项1云请求/最多4原生定位/0重试，原始深度和离线实例不上传，始终无硬件派发。

独立核验6616份证据（836764873字节）大小与SHA256，按原CompletionCriteria复算40项
物理记录，结果完全一致。旧4417份原件、冻结档案和诊断脚本哈希也保持不变。33项首尾
严格ID7可见，含静止拒绝样本；20项物理成功中19项首尾可见，development-043002末端
标记UNKNOWN，全程可见性仍未证明。formal_research=NOT_ACCEPTED、原生动作资格
UNKNOWN_NOT_GRANTED、qualified_groups_added=0。完整raw/运行数据库继续只保存在本地；
源端派生交付记录见 artifacts/research/process/20261114-visible-cuboid-geometry/verification-summary.json。
