# Molmo2-ER + OpenCV + 云端技能规划

此入口实现用户选定的分工：Molmo2-ER 只接收 RGB 并定位；原始对齐 optical-z float32 米制深度用于程序几何；OpenCV 检查初始目标/区域；现有选定云端模型只输出技能顺序；原 `PlanningPipeline` 校验并补齐可信合同字段。

新路径是显式启用的开发入口。当前默认在线服务与历史冻结运行不自动切换。保留现有顶视相机、可见姿态标记、控制器、SafetyShield 和动作证据门。

## 接口

- `vision/molmo_pointing.py`：严格单点/ABSENT 解析、观测/RGB/查询绑定、一次 BF16 加载和有界生成。原始输出、token IDs、处理器摘要与失败记录写入本地 raw。
- `vision/planner.py`：共享 `ground_observation` 与 `build_grounded_contract`；原 `RGBDPlannerAdapter` 接口保持兼容。
- `vision/grounded_planner.py`：任务描述、OpenCV 检查、技能专用云端请求与现有 profile/secret-store 工厂。
- `scripts/probe_molmo_grounded_planner.py`：空运行、回放及真实本地诊断；没有派发或硬件执行选项。

任务描述必须来自用户指令或调用方显式配置，指令逐字匹配。模型接收两个单 RGB 查询：`visible top center of ...`、`interior of ...`。每个结果只能有一个点，0..1000 坐标按现有协议转换一次；1000 对应最后一个像素。多个点、矛盾拒答、非法坐标或错误绑定均关闭候选生成。检出状态不是成功概率，不补造模型置信度。

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

## 证据与验收

`report.json` 分开记录模式、加载/生成启动及完成数、API 夹具、付费请求启动、几何状态和规划管线结果；成功或异常结束均生成 `raw-manifest.local.json`，对实际保留的输入、原生 token/响应与云端请求/响应正文逐文件记录 SHA256；raw 与清单仅保存在本地。云端正文记录不含认证头。每次真实调用的原始证据不可用派生摘要替代。

软件集成、回放、真实本地、真实云端、物理与正式研究分别验收。开发筛选与单次诊断不代表 heldout/G1/G2、正式实验或实机成功。完整批量 raw、权重、SDK、运行数据库和凭据遵循项目既有本地边界。
