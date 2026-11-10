# Molmo2-ER + OpenCV + 云端技能规划

此入口实现用户选定的分工：Molmo2-ER 只接收 RGB 并定位；原始对齐 optical-z float32 米制深度用于程序几何；OpenCV 检查初始目标/区域；现有选定云端模型只输出技能顺序；原 `PlanningPipeline` 校验并补齐可信合同字段。

新路径是显式启用的开发入口。当前默认在线服务与历史冻结运行不自动切换。保留现有顶视相机、可见姿态标记、控制器、SafetyShield 和动作证据门。

## 接口

- `vision/molmo_pointing.py`：严格单点/ABSENT 解析、观测/RGB/查询绑定、一次 BF16 加载和有界生成。原始输出、token IDs、处理器摘要与失败记录写入本地 raw。
- `vision/point_association.py`：低饱和背景点的有界局部颜色关联，保留原生点并独立记录几何采样点。
- `vision/planner.py`：共享 `ground_observation` 与 `build_grounded_contract`；原 `RGBDPlannerAdapter` 接口保持兼容。
- `vision/grounded_planner.py`：任务描述、OpenCV 检查、技能专用云端请求与现有 profile/secret-store 工厂。
- `scripts/probe_molmo_grounded_planner.py`：空运行、回放及真实本地诊断；没有派发或硬件执行选项。

任务描述必须来自用户指令或调用方显式配置，指令逐字匹配。模型接收两个单 RGB 查询：`visible top center of ...`、`interior of ...`。每个结果只能有一个点，0..1000 坐标按现有协议转换一次；1000 对应最后一个像素。多个点、矛盾拒答、非法坐标或错误绑定均关闭候选生成。检出状态不是成功概率，不补造模型置信度。

当目标原生点落在低饱和背景时，允许一次受限关联：任务短语须严格为 `red|green|blue|yellow` 与 `block|box|cube` 的组合，固定半径为图像短边8%且限定8..24像素。范围内所有面积至少8像素的饱和颜色连通域先计数，恰有一个完整位于窗口内部、颜色一致且原始深度有效的候选时，才选择其完整3×3内部点。多候选、颜色矛盾、截断或无效深度均拒绝，不扩窗或重试。直接落在有色区域的点不平移，放置区点不细化。随后仍进入原有抓取几何和全局颜色唯一性/轮廓检查。这是开发范围内的关联策略，不是经校准的模型误差界。

原生坐标保存在 `native_results` 与 `native_original_pixel_target/destination`；`associated_pixel_target` 是关联建议，`original_pixel_target` 是实际送入几何的原图坐标。`target_point_association` 记录候选、策略、拒绝原因和 helper 源码哈希，不能用关联点改写原生预测或原始采集时间。

原始深度无效、未注册抓取 profile、相机方向不支持、初始颜色支撑不唯一/不完整或观测超过5秒时要求重新观测；未来容差为50毫秒。此版本继续限制于已校准的 MuJoCo 顶视、竖直刚性彩色方块研究范围。初始几何通过不证明连续运动、完整放置或物理任务成功。

云端只允许 `skills` 与 `reason`；空技能表示重观测。有效核心顺序为 MOVE_ABOVE、APPROACH、GRASP、LIFT、MOVE_TO_REGION、PLACE、RELEASE、RETREAT，可在首尾各有一个 HOME。坐标、几何、可信版本/时间、安全覆盖字段不属于云端技能接口。

## 使用现有服务工厂

在已有应用/研究 worker 中，传入当前 `ModelControlService` 和明确选择的 profile；工厂不激活或切换 profile，复用既有安全密钥服务。Sol 保留官方 endpoint、`reasoning_effort` 与 `max_completion_tokens`。

```python
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.vision.grounded_planner import (
    GroundingTaskDescriptor, build_molmo_grounded_planner,
)

task = GroundingTaskDescriptor(
    instruction="Move the red block to the green region.",
    target_phrase="red block",
    destination_phrase="green region",
    target_label="red block",
)
planner = build_molmo_grounded_planner(
    service=existing_model_control_service,
    profile_id=selected_profile_id,
    point_provider=resident_point_provider,
    task=task,
    grasp_profile="mujoco_upright_box_v2",
    allow_paid=False,
)
pipeline = PlanningPipeline(planner=planner)
```

原生 provider 需要专用进程主线程持有模型，控制器独立运行。默认 `allow_paid=False` 会阻止云端请求。只有另行准入的真实云端验证才显式启用该权限；CPU 夹具及回放不算真实云端证据。新规划器不继承历史整系统验收或已接受的运行角色绑定。

## 本机诊断

先准备一个任务描述 JSON，字段对应上例；请求 JSON 使用 `InitialPlanningRequest`，例如相同指令与唯一 request_id。普通回放必须提供原始 observation，禁止刷新归档采集时间。只有 `--mode native --capture-fresh` 可使用 `observation: null` 的请求模板；它从当前默认 S01 相机重新采集，模型先加载，随后取得新帧，并分别保存模板与新采集的请求/RGB/原始深度。普通空运行与回放仍须携带 observation，不修改旧帧时间。

默认空运行只验证配置并报告 NOT_STARTED：

```bash
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python \
  scripts/probe_molmo_grounded_planner.py \
  --request request.json --task-descriptor task.json \
  --output datasets/model-cache/molmo-grounded/dry-run-01
```

原 Molmo 环境不含 OpenCV，使用 R545 的独立启动器在搜索路径末尾追加已安装的应用依赖。它核对 Torch/Transformers 等原版本、原路径和入口文件 SHA，执行 CPU ABI 检查，再原样转交参数；不安装包或修改既有运行时。

```bash
MOLMO_PYTHON="/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/ordered-small-vlm-20261109/runtimes/molmoer-r505/bin/python"
MOLMO_LAUNCHER="artifacts/research/process/20261004-ced-development/astra-rounds/round545-molmo-opencv-runtime-overlay-20261110/implementation/launch_molmo_grounded.py"
"$MOLMO_PYTHON" -B "$MOLMO_LAUNCHER" --preflight
MUJOCO_GL=egl "$MOLMO_PYTHON" -B "$MOLMO_LAUNCHER" \
  --mode native --capture-fresh \
  --request request.json --task-descriptor task.json \
  --model-directory /home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER \
  --asset-manifest /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/asset-manifest.json \
  --output datasets/model-cache/molmo-grounded/native-01
```

native 默认仅验证真实本地识别/几何，云端保持 NOT_PERFORMED；不伪造云端回复。可重复传入最多四对 `--request`/`--task-descriptor`，一次加载，整个运行最多8次生成启动；失败也占生成预算。真实资源检查和共享 GPU 锁必须通过，已有权重清单26个文件必须逐项 SHA 匹配。输出目录必须全新。

`--mode replay --replay-points points.json --replay-cloud cloud.json` 使用绑定到 observation/RGB/query/task SHA 的本地夹具，始终标为 REPLAY/API_FIXTURE，实际模型与付费调用数为0。回放保留真实采集时间，过期结果仍拒绝。

## 云端返回后的同会话新帧复核

显式增加 `--post-cloud-revalidate` 可验证云端延迟超过初始观测寿命的情况。该开关要求 `--mode native --capture-fresh --allow-paid`、恰好一对请求/任务描述，以及 `--generation-limit 4` 或更高；本轮真实验证仍严格限定一次加载、四次生成启动、一次付费请求，不重试。默认不开启时，继续按原采集时间执行 5 秒寿命和 50 毫秒未来容差检查。

入口在模型加载后开启一个 `MuJoCoCaptureSession`，第一次采集后进行两次 RGB 定位和现有云端技能规划。只有云端回复通过严格 JSON、非空技能及原有顺序校验，才在同一暂停会话调用一次新的 `capture()`；两帧之间不重置场景、不执行物理步进。第二帧重新执行两次原生定位、OpenCV、原始深度几何和跟踪检查，合同只使用第二帧的观测、几何与原管线生成的可信字段。原请求对象和初始证据不被重写。

复核策略 `paused_mujoco_rgb_depth_v1` 要求相同场景、会话、校准、内参/变换、深度约定、尺寸与仿真时间；新观测必须有新的 ID、checksum 和云端返回后实际采集时间。RGB SHA、有效深度掩码，以及重新计算的目标和放置区支撑掩码 SHA 必须相同。全部有效像素的原始米制深度差要求最大绝对值 ≤0.010 m、RMS ≤0.002 m、绝对有符号均值 ≤0.00025 m。阈值用于同一暂停 MuJoCo 场景的工程异常筛查，不是传感器误差界、物体身份或物理稳定性证明。每次新定位及合同生成后仍检查新帧 5 秒寿命；任一绑定、策略或新几何检查失败均要求重新观测，不沿用旧几何。

原始两帧分别保存于 `raw/capture-01` 和 `raw/refresh-01`，含 RGB、原始 float32 深度、valid mask 和请求诊断快照；后者快照包含新帧，仅用于审计，不替换原 API 请求。`report.json` 区分 `initial_observation_checksum`、成功合同时的 `final_observation_checksum`、补帧启动/完成数与复核状态。最终证据顶层只包含新帧的两次 `native_results`，`cloud_reference` 保留初始两次定位及几何，成功路径总计两帧、四次定位、零张云端图像。元数据一致性本身不能证明不可信调用方实际重新采集；CLI 的受控 `capture()` 调用记录承担采集边界证据。

最终合同构造完成后，原管线还会执行一次该调用专属的私有准入检查；相同请求读取已缓存的 `PLANNED` 时也必须通过。检查保留可信新帧和原请求/任务/规划器/供应器/云端角色与配置绑定，不从可修改的公开 evidence 重建权限。私有回调不进入 Pydantic 的 JSON、schema 或公开字段；序列化回读不能恢复执行资格。相同有效缓存返回原响应；过期、绑定改变、回调丢失或异常则返回新的 `REQUEST_MORE_OBSERVATION` 响应，合同与派发均为空，响应和最后一次验证均失败，并用拒绝结果替换缓存；不重采、不生成、不重复付费。先前已经交给调用方的响应不会被追溯修改，新计划需使用新请求流程。

局部新帧复核确实通过时保留 `post_cloud_revalidation.status=PASSED`，最终出口另记 `final_plan_admission` 的 PASSED/REJECTED、`final_contract`/`cache_hit` 阶段和拒绝原因。缓存有效时保留最初证据与可信时间，不刷新它们。角色来源 SHA 清单包含最终准入所用的 `cloud/planning/models.py` 与 `pipeline.py`，便于与实际代码绑定。

## 证据与验收

`report.json` 分开记录模式、加载/生成启动及完成数、API 夹具、付费请求启动、几何状态和规划管线结果；成功或异常结束均生成 `raw-manifest.local.json`，对实际保留的输入、原生 token/响应与云端请求/响应正文逐文件记录 SHA256；raw 与清单仅保存在本地。云端正文记录不含认证头。每次真实调用的原始证据不可用派生摘要替代。

软件集成、回放、真实本地、真实云端、物理与正式研究分别验收。开发筛选与单次诊断不代表 heldout/G1/G2、正式实验或实机成功。完整批量 raw、权重、SDK、运行数据库和凭据遵循项目既有本地边界。
